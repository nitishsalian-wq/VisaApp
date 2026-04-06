# VisaDesk Deployment Guide for DigitalOcean App Platform

This guide walks you through deploying the VisaDesk Flask application to DigitalOcean's App Platform.

## Prerequisites

- GitHub account with your VisaDesk repository
- DigitalOcean account (free account available)
- Access to environment variables and secrets for your deployment

## Deployment Steps

### Step 1: Prepare Your Repository

1. **Clone the repository locally** (if you haven't already):
   ```bash
   git clone <your-github-repo-url>
   cd visadesk
   ```

2. **Verify deployment files are in place**:
   - `requirements.txt` - includes gunicorn and psycopg2-binary
   - `wsgi.py` - WSGI entry point
   - `Procfile` - defines how to run the app
   - `runtime.txt` - specifies Python 3.11
   - `init_db.py` - database initialization script
   - `.do/app.yaml` - DigitalOcean App Platform config
   - `.env.example` - template for environment variables

3. **Update .do/app.yaml with your GitHub repo**:
   Open `.do/app.yaml` and replace the placeholder:
   ```yaml
   github:
     repo: your-github-username/your-repo-name
     branch: main
   ```

4. **Commit and push all changes**:
   ```bash
   git add .
   git commit -m "Add deployment configuration for DigitalOcean"
   git push origin main
   ```

### Step 2: Create DigitalOcean App

1. **Log in to DigitalOcean Console**:
   - Go to https://cloud.digitalocean.com
   - Log in to your account

2. **Create a new App**:
   - Click on "Apps" in the left sidebar
   - Click "Create App"
   - Choose "GitHub" as the source
   - Authorize DigitalOcean to access your GitHub account (if prompted)
   - Select your VisaDesk repository
   - Select the `main` branch
   - Click "Next"

3. **Configure the App from app.yaml**:
   - DigitalOcean may auto-detect the `.do/app.yaml` file
   - If not, you can manually upload the app.yaml content
   - Review the configuration and click "Next"

### Step 3: Configure Environment Variables and Secrets

1. **Set Environment Variables**:
   Before deploying, you need to configure these secrets in DigitalOcean:

   - **SECRET_KEY**: Generate a strong random key
     ```bash
     python -c "import os; print(os.urandom(32).hex())"
     ```
     Set this as a SECRET in DigitalOcean

   - **DATABASE_URL**: DigitalOcean provides this automatically when you add the PostgreSQL database
     - It will be in the format: `postgresql://user:password@host:port/database`
     - Set this as a SECRET in DigitalOcean

   - **ADMIN_PASSWORD**: Set a strong password for the admin user
     - Example: `ChangeMe@2024` (use a secure password)
     - Set this as a SECRET in DigitalOcean

2. **Add Secrets in DigitalOcean**:
   - In the "Environment" section of the app configuration
   - Click "Edit" next to each environment variable
   - For SECRET variables, select "Encrypt" checkbox
   - Enter the value and click "Save"

3. **Database Configuration**:
   - The PostgreSQL database will be created automatically
   - DigitalOcean will set DATABASE_URL automatically
   - Make sure it's configured as a SECRET with scope "RUN_AND_BUILD_TIME"

### Step 4: Deploy the App

1. **Review Configuration**:
   - Check all settings are correct
   - Verify all secrets are set
   - Confirm GitHub connection is authorized

2. **Click "Create App"**:
   - DigitalOcean will begin building and deploying
   - You'll see build logs in real-time
   - The app will be deployed when the build succeeds

3. **Monitor Deployment**:
   - Watch the "Activity" tab for deployment status
   - Check "Logs" if there are any issues
   - The app is ready when status shows "Active"

### Step 5: Access Your App

1. **Get the App URL**:
   - In the app's main page, you'll see the live URL
   - It will be in format: `https://visadesk-xxxxx.ondigitalocean.app`

2. **Log In**:
   - Visit your app URL in a browser
   - You'll be redirected to the login page
   - Use credentials:
     - **Username**: `admin`
     - **Password**: The ADMIN_PASSWORD you set

3. **Change Admin Password**:
   - After first login, go to Admin settings
   - Change the admin password immediately
   - Use a strong, unique password

## Post-Deployment

### Update Admin Password

1. Log in with initial admin credentials
2. Navigate to admin settings
3. Change password and save
4. Log out and log back in to verify

### Monitor the Application

1. **Check Logs**:
   - In DigitalOcean app dashboard, go to "Logs"
   - View runtime logs for any errors

2. **Set Up Alerts** (Optional):
   - Configure health checks
   - Set up error notifications

3. **Database Backups** (Optional):
   - DigitalOcean provides automated backups
   - Configure backup frequency in database settings

## Troubleshooting

### Database Connection Issues

**Error**: `could not connect to server`

**Solution**:
1. Verify DATABASE_URL is set correctly in Environment
2. Check PostgreSQL database is running (green status in DigitalOcean)
3. Restart the app: go to App Settings > Restart

### Admin User Not Created

**Error**: Can't log in with admin/admin123

**Solution**:
1. Check build logs for init_db.py errors
2. The build_command may need to be re-run
3. Manually run through the Console:
   ```bash
   flask init-db
   ```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'X'`

**Solution**:
1. Check requirements.txt includes all dependencies
2. Rebuild the app: Settings > Rebuild and Deploy

### Static Files Not Loading

**Error**: CSS/JavaScript 404 errors

**Solution**:
1. Ensure static/ folder is in git repository
2. Check file permissions (should be 644)
3. Clear browser cache (Ctrl+Shift+Delete)

## Scaling and Performance

### Adjust Gunicorn Workers

Edit `.do/app.yaml`:
```yaml
run_command: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 4
```

More workers = better concurrency, but uses more memory.

### Increase Instance Size

In DigitalOcean app dashboard:
1. Go to App Settings
2. Change `instance_size_slug` from `basic-xs` to `basic-s` or higher
3. Save and redeploy

### Database Optimization

Monitor in DigitalOcean:
1. Database dashboard shows connections and queries
2. If high load, consider upgrading database plan

## Rollback Deployment

If deployment fails or you need to rollback:

1. Go to app's "Activity" tab
2. Find the previous successful deployment
3. Click the three dots menu
4. Select "Rollback to this deployment"

## Continuous Deployment

The app is configured for automatic deployment:

1. Push to `main` branch on GitHub
2. DigitalOcean automatically builds and deploys
3. Check build status in "Activity" tab
4. App updates live when deployment succeeds

## Security Notes

1. **Change Default Admin Password**: Do this immediately after first login
2. **Use Strong Secrets**: Generate random values for SECRET_KEY and ADMIN_PASSWORD
3. **HTTPS**: DigitalOcean automatically provides HTTPS
4. **Database Backups**: Enable automated backups in database settings
5. **Access Control**: Restrict database access to app only

## Support and Resources

- **DigitalOcean Docs**: https://docs.digitalocean.com/products/app-platform/
- **Flask Documentation**: https://flask.palletsprojects.com/
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org/

## Local Development (Reference)

For local development, the app still works as before:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_ENV=development
export SECRET_KEY=dev-secret

# Run locally
python app.py
```

The app will auto-create the SQLite database in development mode.
