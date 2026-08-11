from decimal import Decimal
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def naira_to_kobo(naira_value: float | int | Decimal) -> int:
    """
    Converts a Naira amount to integer Kobo.
    Example: 50000.00 -> 5000000 Kobo
    """
    if naira_value is None:
        return 0
    return int(Decimal(str(naira_value)) * 100)


def kobo_to_naira(kobo_value: int) -> Decimal:
    """
    Converts integer Kobo to Decimal Naira.
    Example: 5000000 -> Decimal('50000.00')
    """
    if kobo_value is None:
        return Decimal('0.00')
    return (Decimal(kobo_value) / Decimal(100)).quantize(Decimal('0.01'))


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler providing standardized error responses across all endpoints.
    Format:
    {
        "success": false,
        "error": {
            "code": "validation_error",
            "message": "Invalid payload provided.",
            "details": {...}
        }
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_code = getattr(exc, 'default_code', 'api_error')
        message = 'An error occurred processing your request.'

        if isinstance(response.data, dict):
            if 'detail' in response.data:
                message = str(response.data['detail'])
                details = response.data
            else:
                message = 'Validation failed.'
                details = response.data
        elif isinstance(response.data, list):
            message = 'Validation failed.'
            details = {'errors': response.data}
        else:
            details = response.data

        response.data = {
            'success': False,
            'error': {
                'code': str(error_code),
                'message': message,
                'details': details
            }
        }

    return response
