# SES inbound OOO — DevOps

App webhook (auto-confirms SNS subscribe):

`https://leadsense.feuji.com/api/webhooks/ses-inbound`

## Accounts (same region: `ap-south-1`)

- SES sending / inbound receipt rule: root account `711391695265`
- S3 + SNS + LeadSense app: LeadSense account `576090750019`

## Values already in app code / `.env.example`

```
SES_INBOUND_S3_BUCKET=leadsense-ses-inbound-ooo
SES_INBOUND_S3_PREFIX=inbound/
```

Do not reuse the bounce topic `leadsense-bounce-alert`.

## Create in LeadSense account

1. S3 bucket `leadsense-ses-inbound-ooo` (prefix `inbound/`).
2. SNS topic `leadsense-ses-inbound`.
3. HTTPS subscription on that topic: `https://leadsense.feuji.com/api/webhooks/ses-inbound`.

## Create in root SES account

Receipt rule for the inbound domain:

1. Store raw MIME in `s3://leadsense-ses-inbound-ooo/inbound/`
2. Publish to `arn:aws:sns:ap-south-1:576090750019:leadsense-ses-inbound`

Allow root SES (`711391695265`) to `s3:PutObject` on that bucket and `sns:Publish` on that topic. LeadSense app IAM user needs `s3:GetObject` on the same bucket.

Restart UAT backend after the AWS side is live.
