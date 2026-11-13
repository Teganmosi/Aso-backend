"""Rewrite stored states to one spelling ('Lagos State' -> 'Lagos'). Safe to re-run."""
from django.db import migrations


def normalize(apps, schema_editor):
    from apps.common.nigeria import normalize_state
    for model in (apps.get_model('vendors', 'VendorProfile'), apps.get_model('accounts', 'Address')):
        for obj in model.objects.only('id', 'state').iterator():
            fixed = normalize_state(obj.state)
            if fixed != obj.state:
                model.objects.filter(pk=obj.pk).update(state=fixed)


class Migration(migrations.Migration):
    dependencies = [
        ('vendors', '0003_vendorprofile_verification_rejection_reason_and_more'),
        ('accounts', '0002_customerprofile_saved_measurements'),
    ]
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
