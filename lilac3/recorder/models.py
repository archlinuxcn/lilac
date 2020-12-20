from django.db import models

class Version(models.Model):
    key = models.CharField(max_length=50, default="")
    oldver = models.CharField(max_length=50, default="")
    newver = models.CharField(max_length=50, default="")
    timestamp = models.DateTimeField(auto_now=True)

class Status(models.Model):
    key = models.CharField(max_length=50, default="")
    status = models.CharField(max_length=30, default="")
    detail = models.CharField(max_length=200, default="")
    timestamp = models.DateTimeField(auto_now=True)
