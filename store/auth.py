from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed

class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        return super().get_token(user)

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        try:
            verification = user.verification
        except Exception:
            verification = None
        if verification and not verification.is_verified:
            raise AuthenticationFailed('Verify both your email address and mobile number before signing in.')
        return data
