"""
Pieces no longer wait for approval: anything still waiting goes live now.
Pieces Aso sent back for changes (REJECTED) stay hidden until the designer saves a fix.
"""
from django.db import migrations


def publish_waiting(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    Product.objects.filter(approval_status='PENDING').update(approval_status='APPROVED', rejection_reason=None)


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0006_plain_admin_labels'),
    ]

    operations = [
        migrations.RunPython(publish_waiting, migrations.RunPython.noop),
    ]
