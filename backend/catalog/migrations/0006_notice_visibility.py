from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies=[('catalog','0005_activity_draft_guide_draft')]
    operations=[migrations.AddField(model_name='notice',name='visibility',
        field=models.CharField('公开状态',choices=[('public','公开'),('hidden','隐藏')],default='public',max_length=10))]
