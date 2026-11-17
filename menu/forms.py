import re

from django import forms

from .models import Order


class CheckoutForm(forms.Form):
    name = forms.CharField(max_length=100, label="Nombre")
    phone = forms.CharField(max_length=30, label="Teléfono")
    fulfillment = forms.ChoiceField(choices=Order.Fulfillment.choices)
    address = forms.CharField(max_length=250, required=False)
    locality = forms.CharField(max_length=100, required=False)
    reference = forms.CharField(max_length=250, required=False)

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        digits = re.sub(r"\D", "", phone)
        if not re.fullmatch(r"[+\d\s()\-]+", phone) or not 8 <= len(digits) <= 15:
            raise forms.ValidationError("Ingresá un teléfono válido, con código de área.")
        return phone

    def clean(self):
        data = super().clean()
        if data.get("fulfillment") == Order.Fulfillment.DELIVERY:
            if not data.get("address"):
                self.add_error("address", "Ingresá la dirección de entrega.")
            if not data.get("locality"):
                self.add_error("locality", "Ingresá la localidad de entrega.")
        else:
            data["address"] = ""
            data["locality"] = ""
            data["reference"] = ""
        return data


