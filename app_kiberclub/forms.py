from django import forms
from .models import BroadcastMessage

class BroadcastMessageForm(forms.ModelForm):
    class Meta:
        model = BroadcastMessage
        fields = '__all__'
        widgets = {
            'message_text': forms.Textarea(attrs={'rows': 4}),
        }