from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("unicom/", include("unicom.urls")),
    path("unicrm/", include("unicrm.urls")),
    path("unibot/", include("unibot.urls")),
    path("", include("core.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

