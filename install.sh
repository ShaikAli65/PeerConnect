#!/bin/bash

# Variables
URL="https://github.com/ShaikAli65/PeerConnect/tarball/dev"  # Change this to your actual URL
TAR_FILE="downloaded.tar.gz"

# Download the tarball
echo "Downloading tarball from $URL..."
curl -L "$URL" -o "$TAR_FILE"

# Check if download was successful
if [ $? -ne 0 ]; then
    echo "Download failed!"
    exit 1
fi

# Extract the tarball (automatically detects folder name)
echo "Extracting $TAR_FILE..."
tar -xzvf "$TAR_FILE"

# Check if extraction was successful
if [ $? -ne 0 ]; then
    echo "Extraction failed!"
    exit 1
fi

# Get the extracted folder name
EXTRACTED_DIR=$(tar -tzf "$TAR_FILE" | head -1 | cut -f1 -d"/")

# Set execute permissions
chmod +x "$EXTRACTED_DIR/bin/peerconnect.sh"

# Cleanup
rm "$TAR_FILE"

echo "Download and extraction complete! Folder: $EXTRACTED_DIR"
