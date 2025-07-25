#!/bin/bash

echo "A1 Exploit Generator - Grok-4-0709 Setup"
echo "========================================"

# Check for required tools
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ $1 is not installed. Please install it first."
        exit 1
    else
        echo "✅ $1 is installed"
    fi
}

echo "Checking prerequisites..."
check_command python3
check_command pip3
check_command docker
check_command docker-compose
check_command git

# Create virtual environment
echo ""
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Solidity compilers
echo "Installing Solidity compilers..."
python -m solcx.install v0.8.19
python -m solcx.install v0.8.17
python -m solcx.install v0.8.13

# Setup environment file
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your API keys!"
fi

# Create directories
echo "Creating directories..."
mkdir -p results logs config/agents

# Make scripts executable
chmod +x run_scan.py
chmod +x setup.sh

# Docker setup
echo ""
echo "Setting up Docker containers..."
docker-compose build

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys (GROK_API_KEY, ETH_RPC_URL, etc.)"
echo "2. Start services: docker-compose up -d"
echo "3. Run scanner: python run_scan.py <contract_address>"
echo ""
echo "Example: python run_scan.py 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"