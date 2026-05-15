from django.shortcuts import render
from .serializers import AdManagerProfileSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

class AdManagerView(APIView): 
    permission_classes = [IsAuthenticated]

    def post(self, request): 
        serializer = AdManagerProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response({"success: Your account has been created!"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)