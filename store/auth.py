from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        return super().get_token(user)

    def validate(self, attrs):
        # Public login identifier is the verified mobile number; username remains an internal Django field.
        mobile = attrs.pop('mobile', None) or attrs.get('username', '')
        if mobile:
            from .models import UserVerification
            verification = UserVerification.objects.select_related('user').filter(phone=mobile).first()
            if not verification or not verification.phone_verified:
                from rest_framework.exceptions import AuthenticationFailed
                raise AuthenticationFailed('No verified account was found for this mobile number.')
            attrs['username'] = verification.user.username
        data = super().validate(attrs)
        user = self.user
        try:
            verification = user.verification
        except Exception:
            verification = None
        if verification and not verification.is_verified:
            raise AuthenticationFailed('Verify both your email address and mobile number before signing in.')
        return data
