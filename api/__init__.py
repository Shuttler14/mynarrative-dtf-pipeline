# DTF Automation API
# Main entry point for Vercel deployment

# Import the main app from dtf_pipeline
from api.dtf_pipeline import app

# For Vercel serverless
handler = app