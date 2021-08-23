import app.views as views
from django.conf.urls import url

urlpatterns = [
    url(r'^$', views.template),

    url(r'^api/factorial/?$', views.call_worker),
]
