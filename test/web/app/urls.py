from django.conf.urls import url

import app.views as views

urlpatterns = [
    url(r'^$', views.template),

    url(r'^api/factorial/?$', views.call_worker),
]

