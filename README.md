# VM Deployment System

A streamlined repository for managing VM deployments and configurations with automated CI/CD via GitHub Actions.

## Overview

This repository contains the essential VM deployment infrastructure, focused on providing a clean and simple deployment system with both manual and automated deployment options.

## 🚀 Deployment Options

### Automated Deployment (Recommended)

**GitHub Actions automatically deploys to your VM when you push to `main`.**

- ✅ Triggers on every push to `main` branch
- ✅ Handles code sync, dependencies, service restart, and health checks
- ✅ Provides detailed logs and status notifications
- ✅ Can be triggered manually from the Actions tab

**Setup:** See [`.github/DEPLOYMENT_SETUP.md`](.github/DEPLOYMENT_SETUP.md) for complete configuration instructions.

**Quick start:**
1. Configure GitHub Secrets (8 required secrets)
2. Push code to `main` - deployment happens automatically
3. Monitor progress in the `Actions` tab

### Manual Deployment

For local development or when you need direct control.

## VM Deployment Scripts

All deployment and management scripts are located in the `vm/` directory:

- **`deploy.sh`** - Main deployment script for the VM
- **`ssh.sh`** - SSH access to the VM
- **`status.sh`** - Check VM status
- **`logs.sh`** - View VM logs
- **`health_check.sh`** - Health check script
- **`config.example.sh`** - Configuration template

### Manual Quick Start

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

## 📚 Documentation

- **[`.github/DEPLOYMENT_SETUP.md`](.github/DEPLOYMENT_SETUP.md)** - Complete GitHub Actions setup guide
- **[`.github/README.md`](.github/README.md)** - GitHub Actions quick reference
- **[`vm/README.md`](vm/README.md)** - Detailed VM deployment documentation

## 🎯 Typical Workflow

### For Automated Deployments:
```bash
# 1. Make changes to vm_server code or workflow JSON
vim vm_server/server.py

# 2. Commit and push
git add vm_server/
git commit -m "Update memory MCP"
git push origin main

# 3. Deployment happens automatically!
# Monitor: https://github.com/Joru-chan/assistant/actions
```

### For Manual Deployments:
```bash
# 1. Make changes
vim vm_server/server.py

# 2. Deploy manually
./vm/deploy.sh

# 3. Check status
./vm/status.sh
```

## 🔐 Security

- **Never commit secrets** - Configuration files with sensitive data (like `vm/config.sh`) are gitignored
- **Use GitHub Secrets** - Store sensitive data securely in repository settings for automated deployments
- **SSH keys** - Use dedicated deploy keys with minimal permissions
- **Environment variables** - Keep API keys and tokens on the VM, not in the repository

## 🛠️ What's Deployed

The `vm_server/` directory contains a FastMCP server with a minimal memory-only
toolset used by Poke:
- `call_memory_distiller_daily`
- `call_memory_recall_brief_to_poke`

See these docs for details:
- [`vm_server/README.md`](vm_server/README.md)
- [`docs/POKE_MEMORY_WORKFLOWS.md`](docs/POKE_MEMORY_WORKFLOWS.md)
- [`docs/MEMORY_MCP_OPERATIONS.md`](docs/MEMORY_MCP_OPERATIONS.md)

## 🔍 Monitoring

### Automated Deployments
- **Status:** Check the `Actions` tab in GitHub
- **Logs:** Click on any workflow run for detailed logs
- **Notifications:** GitHub sends emails for failed deployments

### Manual Deployments
- **Service status:** `./vm/status.sh`
- **Live logs:** `./vm/logs.sh`
- **Health check:** `./vm/health_check.sh`

## 🆘 Troubleshooting

### Automated Deployment Issues
See [`.github/DEPLOYMENT_SETUP.md#troubleshooting`](.github/DEPLOYMENT_SETUP.md#-troubleshooting)

### Manual Deployment Issues
See [`vm/README.md`](vm/README.md)

### Common Issues
- **SSH connection fails:** Verify SSH key permissions and VM accessibility
- **Service not starting:** Check logs with `./vm/logs.sh` or `sudo journalctl -u mcp-server.service`
- **Health checks fail:** Verify service is running and endpoints are accessible

## 📦 Repository Structure

```
assistant/
├── .github/
│   ├── workflows/
│   │   └── deploy.yml          # GitHub Actions deployment workflow
│   ├── DEPLOYMENT_SETUP.md     # Setup guide for automated deployment
│   └── README.md               # GitHub Actions quick reference
├── vm/
│   ├── deploy.sh               # Manual deployment script
│   ├── config.example.sh       # Configuration template
│   └── ...                     # Other VM management scripts
├── vm_server/
│   ├── server.py               # FastMCP server entry point
│   ├── tools/                  # MCP tools directory
│   └── requirements.txt        # Python dependencies
└── README.md                   # This file
```

## 🎓 Getting Started

**For automated deployment (recommended):**
1. Read [`.github/DEPLOYMENT_SETUP.md`](.github/DEPLOYMENT_SETUP.md)
2. Configure GitHub Secrets
3. Push code to `main` branch

**For manual deployment:**
1. Read [`vm/README.md`](vm/README.md)
2. Set up `vm/config.sh`
3. Run `./vm/deploy.sh`

## 📄 License

See `LICENSE` file for details.

---

**Deployment Status:** ![Deployment](https://github.com/Joru-chan/assistant/actions/workflows/deploy.yml/badge.svg)
