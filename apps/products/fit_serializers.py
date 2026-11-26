from rest_framework import serializers

class FitEstimateRequestSerializer(serializers.Serializer):
    category = serializers.CharField(required=False, default='tops_senator', max_length=40)
    sex = serializers.CharField(required=False, allow_blank=True, default='', max_length=10)
    rtw_size = serializers.CharField(required=False, default='M')
    height_inches = serializers.FloatField(required=False, default=70.0, min_value=48, max_value=90)
    build = serializers.CharField(required=False, default='regular')
    usual_size_fit = serializers.CharField(required=False, default='fitted')
    garment_fit = serializers.CharField(required=False, default='regular')
    style = serializers.CharField(required=False, default='standard')
    known_measurements = serializers.DictField(required=False, default=dict)
    text_description = serializers.CharField(required=False, allow_blank=True, max_length=500)


class FitFeedbackSerializer(serializers.Serializer):
    fit_estimate_id = serializers.UUIDField(required=False)
    order_item_id = serializers.UUIDField(required=False)
    estimated_measurements = serializers.DictField(required=False, default=dict)
    final_measurements = serializers.DictField(required=True)
    tailor_feedback = serializers.CharField(required=False, default='PERFECT')
    notes = serializers.CharField(required=False, allow_blank=True)
