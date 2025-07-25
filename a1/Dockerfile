FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    make \
    curl \
    wget \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Foundry for Ethereum tooling
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup

# Add Foundry to PATH
ENV PATH="/root/.foundry/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Solidity compiler
RUN python -m solcx.install v0.8.19
RUN python -m solcx.install v0.8.17
RUN python -m solcx.install v0.8.13

# Copy application code
COPY . .

# Make the scanner executable
RUN chmod +x run_scan.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ETH_RPC_URL=http://localhost:8545

# Default command
CMD ["python", "run_scan.py", "--help"]