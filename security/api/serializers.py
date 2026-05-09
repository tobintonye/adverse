from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta: 
        model = User
        fields = ('id', 'email', 'password')
    
    def validate_email(self, value):
        email = value.lower().strip()

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Unable to create account.")

        return email
    def create(self, validated_data): 
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password']
        )
        user.is_active = False
        user.role = "ad_manager" # set for now
        user.save()
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if email and password:
            user = authenticate(email=email, password=password)
            if user: 
                if not user.is_active:
                    raise serializers.ValidationError("Invalid email or password.")
                data["user"] = user
                return data
            else: 
                raise serializers.ValidationError("Something went wrong, please try again")
        else: 
            raise serializers.ValidationError("Must include 'email' and 'password'.")