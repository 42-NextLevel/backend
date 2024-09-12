from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from django.core.cache import cache
from .models import User
from .utils import EmailManager
from .serializers import UserSerializer, UserCreateSerializer, UserEmailUpdateSerializer

# class UserModelTestCase(TestCase):
#     def test_get_or_create(self):
#         # 새 사용자 생성 테스트
#         user = User.get_or_create(intra_id='dongkseo', profile_image='https://example.com/image.jpg')
#         self.assertIsNotNone(user)
#         self.assertEqual(user.intra_id, 'dongkseo')

#         # 이미 존재하는 사용자 가져오기 테스트  
#         same_user = User.get_or_create(intra_id='dongkseo', profile_image='https://example.com/new_image.jpg')
#         self.assertEqual(user, same_user)

#     def test_get_by_intra_id(self):
#         User.objects.create(intra_id='dongkseo', profile_image='https://example.com/image.jpg')
#         user = User.get_by_intra_id('dongkseo')
#         self.assertIsNotNone(user)
#         self.assertEqual(user.intra_id, 'dongkseo')

#         non_existent_user = User.get_by_intra_id('non_existent')
#         self.assertIsNone(non_existent_user)

# class SerializerTestCase(TestCase):
#     def setUp(self):
#         self.user_data = {
#             'intra_id': 'dongkseo',
#             'profile_image': 'https://example.com/image.jpg',
#             'email': 'test@example.com'
#         }
#         self.user = User.objects.create(**self.user_data)

#     def test_user_serializer(self):
#         serializer = UserSerializer(instance=self.user)
#         self.assertEqual(set(serializer.data.keys()), set(['id', 'intra_id', 'profile_image', 'email']))

#     def test_user_create_serializer(self):
#         data = {'intra_id': 'newuser', 'profile_image': 'https://example.com/new_image.jpg'}
#         serializer = UserCreateSerializer(data=data)
#         self.assertTrue(serializer.is_valid())
#         user = serializer.save()
#         self.assertIsNotNone(user)
#         self.assertEqual(user.intra_id, 'newuser')

#     def test_user_email_update_serializer(self):
#         data = {'email': 'new@example.com'}
#         serializer = UserEmailUpdateSerializer(instance=self.user, data=data)
#         self.assertTrue(serializer.is_valid())
#         updated_user = serializer.save()
#         self.assertEqual(updated_user.email, 'new@example.com')

class APITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(intra_id='dongkseo', profile_image='https://example.com/image.jpg', email='test@example.com')
        self.auth_code_url = reverse('api:auth')
        self.auth_email_url = reverse('api:email') 
        self.auth_token_url = reverse('api:code')
        self.token_refresh_url = reverse('api:token_refresh')
        self.auth_42_info_url = reverse('api:42_info')

    @patch('requests.post')
    @patch('requests.get')
    def test_auth_code_view(self, mock_get, mock_post):
        # Mock 42 API responses
        mock_post.return_value.json.return_value = {'access_token': 'fake_token'}
        mock_get.return_value.json.return_value = {'id': 'dongkseo', 'image': {'link': 'https://example.com/new_image.jpg'}}
        
        response = self.client.post(self.auth_code_url, {'code': 'fake_code'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('registered', response.data)
        self.assertTrue(User.objects.filter(intra_id='dongkseo').exists())
        
    def test_auth_email_view(self):
        self.client.cookies['intra_id'] = 'dongkseo'
        data = {'email': 'new@example.com'}
        response = self.client.post(self.auth_email_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        updated_user = User.objects.get(intra_id='dongkseo')
        self.assertEqual(updated_user.email, 'new@example.com')

    @patch.object(EmailManager, 'varify_auth_code', return_value=True)  
    def test_auth_token_view(self, mock_verify):
        self.client.cookies['intra_id'] = 'dongkseo'
        response = self.client.post(self.auth_token_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh_token', response.cookies)

    def test_custom_token_refresh_view(self):
        # 먼저 토큰을 얻습니다
        self.client.cookies['intra_id'] = 'dongkseo'
        with patch.object(EmailManager, 'varify_auth_code', return_value=True):
            response = self.client.post(self.auth_token_url)
        refresh_token = response.cookies['refresh_token'].value
        
        # refresh 토큰으로 새 access 토큰을 요청합니다  
        self.client.cookies['refresh_token'] = refresh_token
        response = self.client.post(self.token_refresh_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_auth_42_info_view(self):
        response = self.client.get(self.auth_42_info_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('uid', response.data)
        
    # 오류 케이스 테스트
    def test_auth_code_view_no_code(self):
        response = self.client.post(self.auth_code_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
    def test_auth_email_view_invalid_email(self):
        self.client.cookies['intra_id'] = 'dongkseo'  
        data = {'email': 'invalid_email'}
        response = self.client.post(self.auth_email_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
    def test_auth_token_view_invalid_auth_code(self):
        self.client.cookies['intra_id'] = 'dongkseo'
        with patch.object(EmailManager, 'varify_auth_code', return_value=False):
            response = self.client.post(self.auth_token_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
    def test_custom_token_refresh_view_no_token(self):
        response = self.client.post(self.token_refresh_url)  
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # GET 메서드 테스트 (모든 뷰에서 GET 허용되지 않음)
    def test_get_methods_not_allowed(self):
        urls = [self.auth_code_url, self.auth_email_url, self.auth_token_url, self.token_refresh_url]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_auth_42_info_view_post_not_allowed(self):
        response = self.client.post(self.auth_42_info_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)