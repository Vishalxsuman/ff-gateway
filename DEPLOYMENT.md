# FF Gateway — Azure Deployment Guide

Complete step-by-step guide to deploy FF Gateway to Azure App Service
using GitHub Actions CI/CD.

---

## Prerequisites

- Azure subscription with Owner or Contributor access
- Azure CLI installed locally (`az --version`)
- Docker Desktop (for local testing)
- GitHub repository with this code

---

## Step 1: Create Azure Resources

Run these commands in Azure CLI (or Azure Cloud Shell):

```bash
# Variables — change these
RESOURCE_GROUP="rg-esporizon-prod"
LOCATION="eastus"
ACR_NAME="esporizonacr"          # must be globally unique, lowercase
APP_PLAN="asp-ff-gateway"
APP_NAME="ff-gateway-esporizon"  # must be globally unique

# 1. Resource Group
az group create --name $RESOURCE_GROUP --location $LOCATION

# 2. Azure Container Registry
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# Note ACR credentials:
az acr credential show --name $ACR_NAME

# 3. App Service Plan (Linux, B1 minimum for "Always On")
az appservice plan create \
  --name $APP_PLAN \
  --resource-group $RESOURCE_GROUP \
  --is-linux \
  --sku B1

# 4. Web App (container)
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan $APP_PLAN \
  --name $APP_NAME \
  --deployment-container-image-name mcr.microsoft.com/appsvc/staticsite:latest
```

---

## Step 2: Configure Azure App Service Environment Variables

In Azure Portal → App Service → Configuration → Application Settings,
add ALL of the following:

| Setting Name | Value | Notes |
|---|---|---|
| `FF_SESSION_JWT` | Authorized session JWT | Optional when using a provider; mark as **slot setting** |
| `FF_TOKEN_PROVIDER_URL` | Trusted HTTPS token endpoint | Optional; provider must be authorized to issue the session |
| `FF_TOKEN_PROVIDER_SECRET` | Provider bearer secret | Optional; mark as **slot setting** |
| `FF_TOKEN_UPDATE_KEY` | Long random shared secret | Required to authorize `/token/update`; mark as **slot setting** |
| `FF_OB_VERSION` | `OB55` | Update when Garena patches |
| `AES_KEY` | `Yg&tc%DEuh6%Zc^8` | Update if Garena rotates keys |
| `AES_IV` | `6oyZDr22E3ychjM%` | Update if Garena rotates keys |
| `PORT` | `8000` | Must match container EXPOSE |
| `WEBSITES_PORT` | `8000` | Azure App Service container port mapping |
| `LOG_LEVEL` | `INFO` | Set to `WARNING` for production |
| `ENABLE_CACHE` | `true` | |
| `ENABLE_RATE_LIMIT` | `true` | |
| `CORS_ORIGINS` | `https://your-backend.azurewebsites.net` | Restrict in production |

> **Important:** Never put real tokens or provider secrets in source control. Store them in Azure App Settings/Key Vault and mark them as **slot settings**.

Enable **Always On** to prevent cold starts:
- App Service → Configuration → General Settings → Always On → **On**

---

## Step 3: Set Up GitHub Secrets

In your GitHub repository → Settings → Secrets and variables → Actions:

| Secret Name | Value | Where to get it |
|---|---|---|
| `AZURE_CREDENTIALS` | JSON from `az ad sp create-for-rbac` | See below |
| `ACR_REGISTRY` | `esporizonacr.azurecr.io` | Your ACR Login Server |
| `ACR_USERNAME` | ACR admin username | `az acr credential show` |
| `ACR_PASSWORD` | ACR admin password | `az acr credential show` |
| `AZURE_APP_NAME` | `ff-gateway-esporizon` | Your App Service name |

**Generate `AZURE_CREDENTIALS`:**
```bash
az ad sp create-for-rbac \
  --name "ff-gateway-github-actions" \
  --role contributor \
  --scopes /subscriptions/<YOUR_SUB_ID>/resourceGroups/$RESOURCE_GROUP \
  --json-auth
```
Copy the entire JSON output as the `AZURE_CREDENTIALS` secret.

---

## Step 4: Configure ACR Pull in App Service

```bash
# Allow App Service to pull from ACR
az webapp config container set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --docker-registry-server-url https://$ACR_NAME.azurecr.io \
  --docker-registry-server-user $(az acr credential show --name $ACR_NAME --query username -o tsv) \
  --docker-registry-server-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)
```

---

## Step 5: First Deployment

Push to `main`:

```bash
git add ff-gateway/
git commit -m "feat: add FF Gateway"
git push origin main
```

GitHub Actions will:
1. Run pytest (must pass >80% coverage)
2. Build Docker image and push to ACR
3. Deploy container to App Service
4. Smoke-test `/health`

Watch progress in: GitHub → Actions → "Deploy FF Gateway to Azure"

---

## Step 6: Connect Existing Node.js Backend

In your Node.js backend's Azure Application Settings, add:

```
FREEFIRE_API_URL=https://ff-gateway-esporizon.azurewebsites.net
```

In your backend code:
```javascript
const FREEFIRE_API_URL = process.env.FREEFIRE_API_URL;

async function getPlayerInfo(uid, region = 'IND') {
  const res = await fetch(`${FREEFIRE_API_URL}/player/${uid}?region=${region}`);
  return res.json();
}
```

---

## Step 7: Configure Health Probe

Azure App Service → Health check:
- **Path:** `/health`
- **Interval:** 30 seconds (default)

This ensures Azure restarts the container if the gateway becomes unhealthy.

---

## Monitoring (Application Insights)

```bash
# Create Application Insights
az monitor app-insights component create \
  --app ff-gateway-insights \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP \
  --application-type web

# Link to App Service
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY=$(az monitor app-insights component show \
    --app ff-gateway-insights \
    --resource-group $RESOURCE_GROUP \
    --query instrumentationKey -o tsv)
```

Useful KQL queries in Application Insights:

```kusto
// Error rate over time
requests
| where timestamp > ago(1h)
| summarize errors=countif(resultCode >= 500), total=count() by bin(timestamp, 5m)
| render timechart

// Slow Garena calls
traces
| where message contains "Garena responded"
| extend latency=toreal(extract("([0-9.]+) ms", 1, message))
| summarize avg(latency), max(latency) by bin(timestamp, 10m)
```

---

## Rollback Procedure

```bash
# List recent deployments
az webapp deployment list-publishing-credentials \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP

# Rollback to previous image tag
az webapp config container set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --docker-custom-image-name $ACR_NAME.azurecr.io/ff-gateway:<PREVIOUS_SHA>

# Restart to apply
az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP
```

Or via GitHub: re-run a previous workflow run in GitHub Actions.

---

## Manual Checklist

- [ ] Azure resource group created
- [ ] ACR created with admin enabled
- [ ] App Service Plan created (Linux, B1+)
- [ ] Web App created
- [ ] All 12+ Application Settings configured in Azure Portal
- [ ] `WEBSITES_PORT=8000` set
- [ ] Always On enabled
- [ ] GitHub Secrets: AZURE_CREDENTIALS, ACR_REGISTRY, ACR_USERNAME, ACR_PASSWORD, AZURE_APP_NAME
- [ ] ACR pull permissions set on App Service
- [ ] First push to `main` triggered and CI passed
- [ ] `/health` returns `{ "status": "healthy" }`
- [ ] Node.js backend has `FREEFIRE_API_URL` set
- [ ] Health probe configured in Azure
- [ ] Application Insights connected (optional)
