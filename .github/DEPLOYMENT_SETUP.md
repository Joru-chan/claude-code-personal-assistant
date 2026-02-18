# GitHub Actions Deployment Setup

This guide will help you configure automated deployment to your VM using GitHub Actions.

## 📋 Prerequisites

- GitHub repository with admin access
- SSH access to your VM
- SSH private key for authentication
- VM with systemd service configured

## 🔐 Required GitHub Secrets

You need to configure the following secrets in your GitHub repository:

**Navigation:** `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

### 1. VM_SSH_PRIVATE_KEY
**Value:** Content of your SSH private key

```bash
# To get the content (on your local machine):
cat /Users/jordane/Downloads/ssh-key-2025-11-05.key
```

**Important:** Copy the entire key including the header and footer:
```
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

### 2. VM_HOST
**Value:** `134.98.141.19`

Your VM's IP address or hostname.

### 3. VM_USER
**Value:** `ubuntu`

The SSH username for connecting to your VM.

### 4. VM_DEST_DIR
**Value:** `/home/ubuntu/mcp-server-template/src`

The target directory on the VM where code will be deployed.

### 5. VM_SERVICE
**Value:** `mcp-server.service`

The systemd service name to restart after deployment.

### 6. VM_VENV_PY
**Value:** `/home/ubuntu/mcp-server-template/src/venv/bin/python`

Path to the Python interpreter in your VM's virtual environment.

### 7. VM_MCP_URL
**Value:** `https://mcp-lina.duckdns.org/mcp`

The MCP endpoint URL for health checks.

### 8. VM_HEALTH_URL
**Value:** `https://mcp-lina.duckdns.org/health`

The HTTP health check endpoint URL.

## 🎯 Setting Up Secrets (Step by Step)

### Option A: Via GitHub Web Interface

1. Go to your repository: https://github.com/Joru-chan/assistant
2. Click `Settings` (top navigation)
3. In the left sidebar, click `Secrets and variables` → `Actions`
4. Click `New repository secret`
5. Add each secret from the list above
6. Click `Add secret` to save

### Option B: Via GitHub CLI (if installed)

```bash
# Install GitHub CLI if you haven't: https://cli.github.com/

# Login to GitHub
gh auth login

# Set secrets (replace values with your actual values)
gh secret set VM_SSH_PRIVATE_KEY < /Users/jordane/Downloads/ssh-key-2025-11-05.key
gh secret set VM_HOST -b "134.98.141.19"
gh secret set VM_USER -b "ubuntu"
gh secret set VM_DEST_DIR -b "/home/ubuntu/mcp-server-template/src"
gh secret set VM_SERVICE -b "mcp-server.service"
gh secret set VM_VENV_PY -b "/home/ubuntu/mcp-server-template/src/venv/bin/python"
gh secret set VM_MCP_URL -b "https://mcp-lina.duckdns.org/mcp"
gh secret set VM_HEALTH_URL -b "https://mcp-lina.duckdns.org/health"
```

## ✅ Verifying Setup

After adding all secrets:

1. Go to `Actions` tab in your repository
2. You should see the "Deploy to VM" workflow
3. Click on it
4. Click `Run workflow` → `Run workflow` to trigger a manual deployment
5. Watch the logs to verify everything works

## 🚀 How It Works

### Automatic Deployments

Once configured, deployments happen automatically when you:
- Push code to the `main` branch
- Modify files in `vm_server/`
- Update `vm/deploy.sh`
- Update the workflow file itself

### Manual Deployments

You can trigger deployments manually:
1. Go to `Actions` → `Deploy to VM`
2. Click `Run workflow`
3. Optionally check "Restart only" to skip code sync and dependencies
4. Click `Run workflow`

### What the Workflow Does

1. **Setup SSH** - Configures SSH connection to your VM
2. **Sync Code** - Uses rsync to deploy `vm_server/` directory
3. **Install Dependencies** - Runs `pip install -r requirements.txt` on VM
4. **Restart Service** - Restarts the systemd service
5. **Health Checks** - Verifies deployment via MCP and HTTP endpoints
6. **Cleanup** - Removes SSH keys from runner

## 🔍 Monitoring Deployments

### View Deployment Status

- `Actions` tab shows all workflow runs
- Green checkmark = successful deployment
- Red X = failed deployment
- Click on any run to see detailed logs

### Email Notifications

By default, GitHub sends email notifications for:
- Failed workflows
- Fixed workflows (after a failure)

Configure notifications: `Settings` → `Notifications` → `Actions`

## 🛡️ Security Best Practices

### SSH Key Security
- ✅ Use a dedicated deploy key (not your personal SSH key)
- ✅ Restrict key permissions on VM (add to `authorized_keys` with restrictions)
- ✅ Rotate keys periodically
- ✅ Never commit SSH keys to the repository

### VM Security
- ✅ Keep VM system packages updated
- ✅ Use firewall rules to restrict access
- ✅ Monitor deployment logs for suspicious activity
- ✅ Use SSH key authentication only (disable password auth)

### GitHub Security
- ✅ Enable two-factor authentication
- ✅ Use environment protection rules (optional)
- ✅ Review workflow run logs regularly
- ✅ Limit repository access to trusted collaborators

## 🚧 Troubleshooting

### Deployment Fails with "SSH connection failed"
- Verify `VM_SSH_PRIVATE_KEY` contains the complete key
- Check that the key format is correct (OpenSSH format)
- Verify `VM_HOST` and `VM_USER` are correct
- Ensure VM is accessible from GitHub Actions runners

### Service Restart Fails
- Check that `VM_SERVICE` name is correct
- Verify the user has sudo permissions without password prompt
- Check systemd service configuration on VM

### Health Check Fails
- Verify `VM_MCP_URL` and `VM_HEALTH_URL` are correct
- Check that the service is actually running: `sudo systemctl status mcp-server.service`
- Review service logs: `sudo journalctl -u mcp-server.service -n 50`
- Verify firewall/network allows access to health endpoints

### Rsync Fails
- Check `VM_DEST_DIR` path exists on VM
- Verify SSH user has write permissions to destination
- Check disk space on VM: `df -h`

## 🔄 Rollback Procedure

If a deployment breaks something:

1. **Quick rollback via GitHub:**
   ```bash
   # Revert the problematic commit locally
   git revert <commit-sha>
   git push origin main
   # This triggers automatic redeployment
   ```

2. **Manual rollback on VM:**
   ```bash
   # SSH into VM
   ssh -i /path/to/key ubuntu@134.98.141.19
   
   # Restore from backup (if you have one)
   # Or manually fix the issue
   
   # Restart service
   sudo systemctl restart mcp-server.service
   ```

## 📝 Environment Protection (Optional)

For additional safety, you can configure environment protection rules:

1. Go to `Settings` → `Environments`
2. Create a new environment called `production`
3. Add protection rules:
   - Required reviewers (require approval before deployment)
   - Wait timer (delay deployment by X minutes)
   - Deployment branches (restrict to `main` only)

Update the workflow file to use this environment (already configured):
```yaml
jobs:
  deploy:
    environment: production  # Already present in workflow
```

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [SSH Key Management](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)

## 🆘 Getting Help

If you encounter issues:
1. Check the workflow logs in the `Actions` tab
2. Review this documentation
3. Check VM logs: `sudo journalctl -u mcp-server.service`
4. Verify all secrets are correctly configured
5. Test SSH connection manually from your local machine

## ✨ Success Checklist

- [ ] All 8 GitHub secrets configured
- [ ] Workflow file committed to repository
- [ ] Manual workflow run successful
- [ ] Automatic deployment on push works
- [ ] Health checks pass
- [ ] Service is running correctly
- [ ] Documentation reviewed and understood

---

**Last Updated:** 2026-02-18  
**Workflow Version:** 1.0  
**Status:** Ready for production use
