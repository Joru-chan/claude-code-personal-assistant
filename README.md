# VM Deployment System

A streamlined repository for managing VM deployments and configurations.

## Overview

This repository contains the essential VM deployment infrastructure, focused on providing a clean and simple deployment system.

## VM Deployment Scripts

All deployment and management scripts are located in the `vm/` directory:

- **`deploy.sh`** - Main deployment script for the VM
- **`ssh.sh`** - SSH access to the VM
- **`status.sh`** - Check VM status
- **`logs.sh`** - View VM logs
- **`health_check.sh`** - Health check script
- **`config.example.sh`** - Configuration template

### Quick Start

1. Copy the example configuration:
   ```bash
   cp vm/config.example.sh vm/config.sh
   ```

2. Edit `vm/config.sh` with your VM details

3. Deploy to your VM:
   ```bash
   ./vm/deploy.sh
   ```

4. Check status:
   ```bash
   ./vm/status.sh
   ```

## Documentation

- **`vm/README.md`** - Detailed VM deployment documentation

## Security

Do not commit secrets. Configuration files with sensitive data (like `vm/config.sh`) should be kept local and added to `.gitignore`.

## License

See `LICENSE` file for details.
