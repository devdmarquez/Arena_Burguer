from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import AboutPhoto


class AboutSectionTests(TestCase):
    def test_official_photos_replace_illustration_and_hidden_photos_are_excluded(self):
        menu = self.client.get(reverse("index"))
        self.assertNotContains(menu, 'id="nosotros"')
        self.assertContains(menu, 'href="/nosotros/"')
        response = self.client.get(reverse("about"))
        self.assertContains(response, 'id="nosotros"')
        self.assertContains(response, 'menu/logo.jpeg')
        self.assertNotContains(response, 'cocina-arena.webp')
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            data = BytesIO()
            Image.new('RGB', (60, 40), 'orange').save(data, format='JPEG')
            photo = AboutPhoto(title='Nuestra cocina', photo=SimpleUploadedFile('local.jpg', data.getvalue(), content_type='image/jpeg'))
            photo.full_clean()
            photo.save()
            response = self.client.get(reverse("about"))
            self.assertContains(response, photo.photo.url)
            self.assertNotContains(response, 'menu/about/cocina-arena.webp')
            photo.active = False
            photo.save()
            response = self.client.get(reverse("about"))
            self.assertNotContains(response, photo.photo.url)
            self.assertNotContains(response, 'cocina-arena.webp')
