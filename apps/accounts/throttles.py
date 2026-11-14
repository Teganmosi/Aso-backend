from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    """Slows password guessing: 10 sign-in attempts per minute per IP."""
    scope = 'login'
    rate = '10/minute'

    def allow_request(self, request, view):
        # Applies to signed-in users too (AnonRateThrottle skips them by default).
        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True
        return super(AnonRateThrottle, self).allow_request(request, view)

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class RegisterThrottle(LoginThrottle):
    scope = 'register'
    rate = '20/hour'


class VerifyEmailThrottle(LoginThrottle):
    """Guessing a 6-digit code: each code also locks after 5 wrong tries."""
    scope = 'verify_email'
    rate = '30/hour'


class ResendCodeThrottle(LoginThrottle):
    """Each send costs email quota (Resend free plan: 100/day)."""
    scope = 'resend_code'
    rate = '8/hour'


class PasswordResetThrottle(LoginThrottle):
    """Reset emails cost money and can be used to spam someone's inbox."""
    scope = 'password_reset'
    rate = '5/hour'
