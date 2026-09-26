#!/usr/bin/env bash
# scripts/regen_protobuf.sh
# ──────────────────────────────────────────────────────────────────────────────
# Regenerate Python protobuf stubs from .proto source files.
# Run this whenever Garena changes the data schema (new OB version).
#
# Prerequisites: protoc + grpc_tools installed
#   pip install grpcio-tools
#
# Usage:
#   chmod +x scripts/regen_protobuf.sh
#   ./scripts/regen_protobuf.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROTO_SRC="src/ff/protobuf/proto"
PROTO_OUT="src/ff/protobuf"

if [ ! -d "$PROTO_SRC" ]; then
  echo "ERROR: Proto source directory '$PROTO_SRC' not found."
  echo "Place your .proto files in: $PROTO_SRC/"
  exit 1
fi

echo "Regenerating protobuf stubs from $PROTO_SRC → $PROTO_OUT ..."

python -m grpc_tools.protoc \
  -I"$PROTO_SRC" \
  --python_out="$PROTO_OUT" \
  "$PROTO_SRC"/*.proto

echo "Done. Files generated:"
ls -la "$PROTO_OUT"/*_pb2.py

echo ""
echo "IMPORTANT: Review generated files before committing."
echo "If field numbers changed, update client.py field mappings accordingly."
