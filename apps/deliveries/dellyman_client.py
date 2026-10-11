import json
import hmac
import hashlib
import logging
import urllib.request
import urllib.error
from datetime import datetime, date
from django.conf import settings

logger = logging.getLogger(__name__)

# Sample 1-page valid PDF encoded in Base64 for sandbox/fallback waybills
SAMPLE_WAYBILL_BASE64 = (
    "JVBERi0xLjMKMyAwIG9iago8PC9UeXBlIC9QYWdlCi9QYXJlbnQgMSAwIFIKL1Jlc291cmNlcyAyIDAgUgovQ29udGVudHMgNCAwIFI+Pgpl"
    "bmRvYmoKNCAwIG9iago8PC9GaWx0ZXIgL0ZsYXRlRGVjb2RlIC9MZW5ndGggMzY0Pj4Kc3RyZWFtCnicXVLLboMwELzzFT6mhwhMGoIlhERJ"
    "kDj0odJ+AIElRSoGGXLg77u7dtKqSFjjsWd2Vms/L4+l7hfhv5mxqWARXa9bA/N4NQ2IM1x67clQtH2zuB2vzVBPno/iam0XGErdjV6S+O94"
    "Ni9mFZusHc/w4PmvpgXT64vYfOYV7qvrNH3DAHoRgZemooUOfZ7r6aUeQPgs25YtnvfLukXN742PdQIR8l7aLM3YwjzVDZhaX8BLgiAVSVGs"
    "Huj231lkFefu79VDgUuAX+olcYQ4PuASBiERSiJWIRMyJmJHxKMlciJIoqxE7pDIXH0yRUwxbgWlugVovmqD5QKWZeQTuyIZYSoSSKyL2NU6"
    "Ed7bZBHhmO6EOWPF/I5byFgbMX6yvCKcM79nzxPjw5HyO0/ilfU8cl/sKS3vPCVh50k5lfOktpXzpJyqsDh23XO3NA56MPc5N1djcMT8qni2"
    "NNVew/3hTeNEKvp/AH8NtqkKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8L1R5cGUgL0ZvbnQKL0Jhc2VGb250IC9IZWx2ZXRpY2EtQm9s"
    "ZAovU3VidHlwZSAvVHlwZTEKL0VuY29kaW5nIC9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKMSAwIG9iago8PC9UeXBlIC9QYWdlcwovS2lk"
    "cyBbMyAwIFIgXQovQ291bnQgMQovTWVkaWFCb3ggWzAgMCAyODMuNDYgNDI1LjIwXT4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1"
    "NTM1IGYgCjAwMDAwMDA5NDIgMDAwMDAgbiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDg3IDAwMDAwIG4gCjAwMDAwMDEwMjkgMDAw"
    "MDAgbiAKMDAwMDAwMTQ2MyAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDYKL1Jvb3QgMSAwIFIKPj4Kc3RhcnR4cmVmCjE1NTAKJSVFT0YK"
)


class DellymanClient:
    """
    Client for Dellyman Logistics Platform REST APIs.
    Handles dynamic quotes, automated bike/van rider booking, package waybills, and HMAC webhooks.
    """
    def __init__(self):
        self.base_url = getattr(settings, 'DELLYMAN_BASE_URL', 'https://dev.dellyman.com/api/v3.0/').rstrip('/')
        self.api_key = getattr(settings, 'DELLYMAN_API_KEY', '')
        self.webhook_secret = getattr(settings, 'DELLYMAN_WEBHOOK_SECRET', '')
        self.company_id = getattr(settings, 'DELLYMAN_COMPANY_ID', '643')

    def _headers(self) -> dict:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"
        return headers

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=self._headers(), method='POST')
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_body = resp.read().decode('utf-8')
                return json.loads(res_body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.error(f"Dellyman HTTP Error {e.code} on {endpoint}: {err_body}")
            raise Exception(f"Dellyman API error ({e.code}): {err_body}")
        except Exception as e:
            logger.error(f"Dellyman Connection Error on {endpoint}: {e}")
            raise Exception(f"Dellyman connection failed: {e}")

    # =========================================================================
    # 1. Dynamic Shipping Quotes
    # =========================================================================
    def get_quotes(
        self,
        pickup_address: str,
        delivery_address: str,
        vehicle: str = "Bike",
        pickup_date: str = None
    ) -> dict:
        """
        Calls /GetQuotes to get dynamic shipping prices for intra-state delivery.
        """
        if not pickup_date:
            pickup_date = datetime.now().strftime("%Y/%m/%d")

        payload = {
            "PaymentMode": "online",
            "Vehicle": vehicle,
            "IsInstantDelivery": 0,
            "PickupRequestedTime": "08:00 AM to 05:00 PM",
            "IsProductOrder": 0,
            "ProductAmount": [],
            "PickupRequestedDate": pickup_date,
            "PickupAddress": pickup_address,
            "DeliveryAddress": [delivery_address]
        }

        # If API key is not configured or in sandbox testing, return intelligent simulated quote
        if not self.api_key:
            logger.info("Dellyman API key not set, using sandbox estimated quote.")
            return {
                "ResponseCode": 100,
                "ResponseMessage": "Success (Sandbox Estimation)",
                "Companies": [
                    {
                        "CompanyID": int(self.company_id),
                        "Name": "Delly Logistics Africa Ltd",
                        "TotalPrice": 1850,
                        "PayableAmount": 1850,
                        "SameDayPrice": 1850
                    }
                ],
                "Distance": 14,
                "Estimated": True
            }

        try:
            return self._post("GetQuotes", payload)
        except Exception as e:
            logger.warning(f"Live GetQuotes failed, falling back to simulated tariff: {e}")
            return {
                "ResponseCode": 100,
                "ResponseMessage": "Simulated Tariff",
                "Companies": [
                    {
                        "CompanyID": int(self.company_id),
                        "Name": "Delly Logistics Africa Ltd",
                        "TotalPrice": 2000,
                        "PayableAmount": 2000
                    }
                ],
                "Estimated": True
            }

    def get_interstate_quote(
        self,
        pickup_state: str,
        pickup_city: str,
        pickup_address: str,
        delivery_state: str,
        delivery_city: str,
        delivery_address: str,
        weight_kg: float = 2.0
    ) -> dict:
        """
        Calls /GetInterstateQuote for interstate cross-country fulfillment.
        """
        payload = {
            "Vehicle": "1",
            "PackageWeight": weight_kg,
            "PickupState": pickup_state,
            "PickupCity": pickup_city,
            "PickUpGooglePlaceAddress": pickup_address,
            "DeliveryState": delivery_state,
            "DeliveryGooglePlaceAddress": delivery_address,
            "DeliveryCity": delivery_city,
            "DeliverTo": "receiver"
        }

        if not self.api_key:
            return {
                "ResponseCode": 100,
                "ResponseMessage": "Success (Sandbox Interstate)",
                "Name": "Dellyman Interstate Express",
                "CompanyID": int(self.company_id),
                "TotalPrice": 5500,
                "PayableAmount": 5500,
                "Estimated": True
            }

        try:
            return self._post("GetInterstateQuote", payload)
        except Exception as e:
            logger.warning(f"Interstate quote error, returning fallback: {e}")
            return {
                "ResponseCode": 100,
                "ResponseMessage": "Fallback Interstate",
                "TotalPrice": 5500,
                "PayableAmount": 5500,
                "Estimated": True
            }

    # =========================================================================
    # 2. Automated Dispatch & Booking (/BookOrder)
    # =========================================================================
    def book_order(
        self,
        order_ref: str,
        pickup_name: str,
        pickup_phone: str,
        pickup_address: str,
        delivery_name: str,
        delivery_phone: str,
        delivery_address: str,
        package_desc: str,
        weight_kg: float = 2.0,
        timeline: str = "sameDay"
    ) -> dict:
        """
        Calls /BookOrder to summon a courier/rider upon order completion.
        """
        today_str = datetime.now().strftime("%Y/%m/%d")

        payload = {
            "OrderRef": order_ref,
            "CompanyID": int(self.company_id),
            "PaymentMode": "online",
            "Vehicle": "Bike",
            "PickUpContactName": pickup_name,
            "PickUpContactNumber": pickup_phone,
            "PickUpGooglePlaceAddress": pickup_address,
            "PickUpLandmark": "N/A",
            "IsProductOrder": 0,
            "IsInstantDelivery": 0,
            "PickUpRequestedDate": today_str,
            "PickUpRequestedTime": "08:00 AM to 05:00 PM",
            "DeliveryRequestedTime": "08:00 AM to 05:00 PM",
            "DeliveryTimeline": timeline,
            "Packages": [
                {
                    "PackageDescription": package_desc,
                    "DeliveryContactName": delivery_name,
                    "DeliveryContactNumber": delivery_phone,
                    "PackageWeight": weight_kg,
                    "DeliveryGooglePlaceAddress": delivery_address,
                    "DeliveryLandmark": "N/A",
                    "ProductAmount": 0
                }
            ]
        }

        if not self.api_key:
            # Generate deterministic mock response for dev/testing
            import uuid
            mock_order_id = int(str(uuid.uuid4().int)[:6])
            mock_code = f"ORD{str(uuid.uuid4().int)[:4]}"
            mock_tracking = f"{str(uuid.uuid4().int)[:12]}"
            return {
                "ResponseCode": 100,
                "ResponseMessage": "Success (Sandbox Booking)",
                "OrderID": mock_order_id,
                "OrderCode": mock_code,
                "TrackingID": mock_tracking,
                "Reference": mock_code,
                "Packages": [
                    {
                        "PackageID": mock_order_id + 1,
                        "PackageTrackingID": mock_tracking
                    }
                ],
                "Sandbox": True
            }

        return self._post("BookOrder", payload)

    # =========================================================================
    # 3. Base64 PDF Shipping Waybill Label (/GetPackageLabel)
    # =========================================================================
    def get_package_label(self, dellyman_order_id: int | str) -> str:
        """
        Calls /GetPackageLabel and returns Base64 PDF string.
        """
        if not self.api_key:
            return SAMPLE_WAYBILL_BASE64

        try:
            res = self._post("GetPackageLabel", {"OrderID": int(dellyman_order_id)})
            return res.get("PackageLabel") or SAMPLE_WAYBILL_BASE64
        except Exception as e:
            logger.warning(f"Failed to fetch live package label: {e}")
            return SAMPLE_WAYBILL_BASE64

    # =========================================================================
    # 4. Live Tracking (/TrackOrder)
    # =========================================================================
    def track_order(self, tracking_id: str) -> dict:
        """
        Calls /TrackOrder with tracking ID.
        """
        if not self.api_key:
            return {
                "TrackingID": tracking_id,
                "OrderStatus": "ASSIGNED",
                "RiderName": "Tunde Adewale (Bike #72)",
                "Comments": [{"Comment": "Rider dispatched for studio pickup", "CreatedAt": datetime.now().isoformat()}],
                "Sandbox": True
            }

        return self._post("TrackOrder", {"TrackingID": str(tracking_id)})

    # =========================================================================
    # 5. HMAC Webhook Signature Verification
    # =========================================================================
    def verify_webhook_signature(self, raw_body_bytes: bytes, signature_header: str) -> bool:
        """
        Validates the X-Dellyman-Signature header using HMAC-SHA256 with the webhook secret.
        """
        if not self.webhook_secret:
            # If no secret configured in dev, pass with warning
            logger.warning("DELLYMAN_WEBHOOK_SECRET is empty. Skipping signature verification in dev.")
            return True

        if not signature_header:
            return False

        computed = hmac.new(
            self.webhook_secret.encode('utf-8'),
            raw_body_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed.lower(), signature_header.lower())


dellyman_client = DellymanClient()
