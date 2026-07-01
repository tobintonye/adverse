from django.urls import path

from .views import (AdManagerEarningsView, CampaignPaymentDetailView, CampaignRefundView, InitiateCampaignPaymentView,
                    PayoutHistoryView, PaystackWebhookView, SubaccountAuditLogView, SubaccountDetailView,
                    SubaccountSetupView, SubaccountUpdateBankView)

app_name = "payments"

urlpatterns = [
    # Subaccount
    path("subaccount/setup/", SubaccountSetupView.as_view(), name="subaccount-setup"),
    path("subaccount/", SubaccountDetailView.as_view(), name="subaccount-detail"),
    path("subaccount/update-bank/", SubaccountUpdateBankView.as_view(), name="subaccount-update-bank"),
    path("subaccount/audit-log/", SubaccountAuditLogView.as_view(), name="subaccount-audit-log"),

    # Campaign Payments
    path("campaigns/pay/", InitiateCampaignPaymentView.as_view(), name="campaign-pay"),
    path("campaigns/<uuid:campaign_id>/payment/", CampaignPaymentDetailView.as_view(), name="campaign-payment-detail"),
    path("campaigns/<uuid:campaign_id>/refund/", CampaignRefundView.as_view(), name="campaign-refund"),
    

    # Ad Manager Earnings
    path("earnings/", AdManagerEarningsView.as_view(), name="earnings"),

    # Payout History
    path("payouts/", PayoutHistoryView.as_view(), name="payout-history"),

    # Paystack Webhook
    # Register this URL in your Paystack dashboard under Settings > Webhooks
    path("webhook/paystack/", PaystackWebhookView.as_view(), name="paystack-webhook"),
]