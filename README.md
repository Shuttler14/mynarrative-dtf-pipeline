# DTF Automation Pipeline

Automated Direct-to-Film (DTF) printing workflow for My Narrative custom apparel.

## Overview

This system automates the DTF printing process after a customer purchases a custom design on Shopify:

1. **Payment received** → Shopify webhook triggers pipeline
2. **Content Safety Check** → OpenAI moderation filters inappropriate content
3. **Image Upscaling** → Ensures 300 DPI print quality (min 3000x3000px)
4. **Background Removal** → rembg for clean, transparent designs
5. **Nesting Optimization** → Bin-packing algorithm for optimal sheet layout
6. **PDF Generation** → CoralDraw-ready print sheets with crop marks

## Quick Start

### 1. Install Dependencies

```bash
cd dtf-automation
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required Environment Variables:**

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for content moderation |
| `AWS_ACCESS_KEY_ID` | AWS S3 access key |
| `AWS_SECRET_ACCESS_KEY` | AWS S3 secret key |
| `AWS_REGION` | AWS region (default: ap-south-1) |
| `S3_BUCKET_NAME` | S3 bucket for storing designs |
| `SHOPIFY_WEBHOOK_SECRET` | Shopify webhook secret |

### 3. Run Locally

```bash
uvicorn api:app --reload --port 8000
```

### 4. Run Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Webhook Endpoint
```
POST /api/webhook/shopify
```
Receives Shopify order webhooks when payment is completed.

### Manual Processing
```
POST /api/process-design
```
Manually trigger design processing (for testing).

### Status Check
```
GET /api/status/{design_uuid}
```
Check processing status of a design.

### Trigger PDF Generation
```
POST /api/trigger-sheet
```
Force generate PDF even if sheet isn't full.

## Shopify Integration

### Setup Webhook in Shopify Admin

1. Go to **Settings → Notifications → Webhooks**
2. Click **Create webhook**
3. Configure:
   - **Event**: Orders updated
   - **URL**: `https://your-vercel-url.vercel.app/api/webhook/shopify`
   - **Format**: JSON
   - **API version**: 2024-01
4. Copy the webhook secret to your `.env` file

### Line Item Properties

Your Shopify product must have these properties:

| Property | Value |
|----------|-------|
| `_design_uuid` | Unique design identifier (e.g., UUID) |
| `_product_type` | "tee" or "hoodie" |

### Storing Designs on S3

Designs should be stored at:
```
s3://{S3_BUCKET}/designs/{user_email}/{design_uuid}.png
```

Preview images at:
```
https://cdn.mynarrative.store/previews/{design_uuid}.jpg
```

## Architecture

```
┌─────────────────┐
│     Shopify      │
│  Payment Webhook │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Vercel API    │
│  (FastAPI)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│ Content Safety  │────►│   OpenAI    │
│ (Moderation)     │     │ Moderation  │
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│ Image Upscaler  │
│ (300 DPI,       │
│ 3000x3000 min)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Background      │
│ Remover (rembg) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Nesting         │
│ Optimizer       │
│ (Bin-packing)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PDF Generator   │
│ (CoralDraw      │
│  compatible)    │
└─────────────────┘
```

## Sheet Specifications

### Standard DTF Sheet Sizes

| Size | Dimensions (mm) | Common Use |
|------|----------------|------------|
| 12x18 inch | 305 x 457 | Standard DTF sheet |
| A3 | 297 x 420 | Larger designs |
| 17x22 inch | 432 x 559 | Bulk printing |

### Design Limits

- Maximum 4 designs per sheet
- 10mm bleed margin between designs
- 15mm edge margin from sheet edge
- Max design size for tees: 250 x 350mm
- Max design size for hoodies: 280 x 380mm

## Output PDF Format

The generated PDF includes:
- Design images in CMYK color space
- Crop marks for each design
- Registration marks
- Job information (sheet ID, date, design count)
- 300 DPI resolution

## Vercel Deployment

### 1. Deploy

```bash
npm i -g vercel
vercel
```

### 2. Add Environment Variables

In Vercel dashboard:
- Go to **Settings → Environment Variables**
- Add all variables from `.env.example`

### 3. Configure Build

```bash
# vercel.json
{
  "builds": [
    {
      "src": "api/*.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/$1"
    }
  ]
}
```

## Manual Setup Tasks (Required)

After deploying, you need to complete these manually:

### 1. Create S3 Bucket
- Go to AWS S3 Console
- Create bucket: `mynarrative-dtf`
- Configure CORS for Vercel access
- Note the bucket name in `.env`

### 2. Create Shopify Webhook
- Go to Shopify Admin → Settings → Notifications → Webhooks
- Create webhook as described above
- Copy webhook secret to Vercel environment variables

### 3. Set Up Shopify Product
- Create product with customization options
- Add line item properties for `_design_uuid` and `_product_type`
- Ensure design images are uploaded to S3 before checkout

### 4. Configure Shopify Theme
- Add JavaScript to capture design UUID when customer customizes
- Store in cart line item properties at checkout

### 5. Test the Pipeline
- Place a test order with a design
- Verify webhook is received in Vercel logs
- Check S3 for processed files
- Verify PDF is generated correctly

### 6. Notify Print Team
- Set up email/Slack notifications for completed sheets
- Configure SMTP credentials in `.env` for email alerts
- Or integrate with Slack webhook for instant notifications

## Troubleshooting

### Webhook Not Received
- Check webhook URL is correct and publicly accessible
- Verify webhook secret matches
- Check Vercel deployment logs

### Content Safety Fails
- Check OpenAI API key is valid
- Check API quota/usage in OpenAI dashboard

### Image Quality Poor
- Ensure original images are high enough resolution
- Check DPI setting (default 300)
- Verify image is being upscaled (check logs)

### Background Not Removed
- Ensure rembg is installed
- Check for white/light backgrounds (works best)
- Try with alpha_matting enabled

### Nesting Not Optimal
- Adjust `max_designs_per_sheet`
- Modify bleed margins if designs are too close
- Check sheet size configuration

### PDF Not Opening in CoralDraw
- Ensure reportlab is installed
- Check PDF is valid with `%PDF` header
- Try basic PDF fallback if reportlab fails

## License

MIT - My Narrative 2024