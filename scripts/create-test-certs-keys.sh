#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
OUTPUT_DIR="$SCRIPT_DIR/../tests"

######################### CA #########################

echo "Generating CA private key and certificate..."

openssl genpkey -algorithm RSA -out "$OUTPUT_DIR"/ca.key.pem

openssl req -new -x509 -days 73050 -key "$OUTPUT_DIR"/ca.key.pem -out "$OUTPUT_DIR"/ca.cert.pem \
    -config "$SCRIPT_DIR"/openssl.cnf -extensions v3_ca -subj "/CN=Test Self-Signed CA"

echo "CA certificate and key created successfully."

######################### SERVER #########################

echo "Generating server private key and CSR..."

openssl genpkey -algorithm RSA -out "$OUTPUT_DIR"/server.key.pem

openssl req -new -key "$OUTPUT_DIR"/server.key.pem -out "$OUTPUT_DIR"/server.csr \
    -config "$SCRIPT_DIR"/openssl.cnf -subj "/CN=localhost/O=Test Server"

echo "Signing the server CSR with the CA certificate..."

openssl x509 -req -in "$OUTPUT_DIR"/server.csr -CA "$OUTPUT_DIR"/ca.cert.pem -CAkey "$OUTPUT_DIR"/ca.key.pem \
    -CAcreateserial -out "$OUTPUT_DIR"/server.cert.pem -days 73050 -extensions v3_req \
    -extfile "$SCRIPT_DIR"/openssl.cnf

echo "Server certificate signed successfully."

######################### CLIENT #########################

echo "Generating client private key and CSR..."

openssl genpkey -algorithm RSA -out "$OUTPUT_DIR"/client.key.pem

openssl req -new -key "$OUTPUT_DIR"/client.key.pem -out "$OUTPUT_DIR"/client.csr \
    -config "$SCRIPT_DIR"/openssl.cnf -subj "/CN=localhost/O=Test Client"

echo "Signing the client CSR with the CA certificate..."

openssl x509 -req -in "$OUTPUT_DIR"/client.csr -CA "$OUTPUT_DIR"/ca.cert.pem -CAkey "$OUTPUT_DIR"/ca.key.pem \
    -CAcreateserial -out "$OUTPUT_DIR"/client.cert.pem -days 73050 -extensions v3_req \
    -extfile "$SCRIPT_DIR"/openssl.cnf

echo "Client certificate signed successfully."

######################### COMPLETE #########################

rm -f "$OUTPUT_DIR"/server.csr "$OUTPUT_DIR"/client.csr

echo "Complete."

