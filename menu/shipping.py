"""Distancias en línea recta y cotizaciones firmadas; sin geocodificar domicilios."""
from decimal import Decimal, ROUND_CEILING
from math import asin, cos, isfinite, radians, sin, sqrt

from django.conf import settings
from django.core import signing


class ShippingError(ValueError):
    pass


def origin():
    lat, lon = float(settings.STORE_LATITUDE), float(settings.STORE_LONGITUDE)
    if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ShippingError("La ubicación del local no está configurada correctamente.")
    return lat, lon


def fee_for_distance(distance):
    value = Decimal(str(distance))
    if not value.is_finite() or value < 0:
        raise ShippingError("La distancia no es válida.")
    if value > 3000:
        raise ShippingError("Esta ubicación está fuera del radio de entrega de 3 km. Podés elegir retiro en el local.")
    bands = int((value / 500).to_integral_value(rounding=ROUND_CEILING))
    return 1000 + 500 * bands


def calculate(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ShippingError("La ubicación de entrega no es válida.")
    store_lat, store_lon = origin()
    p1, p2 = radians(store_lat), radians(lat)
    a = sin(radians(lat - store_lat) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon - store_lon) / 2) ** 2
    distance = round(6371008.8 * 2 * asin(sqrt(min(1, max(0, a)))), 3)
    return distance, fee_for_distance(distance)


def make_quote(address, latitude, longitude):
    distance, fee = calculate(latitude, longitude)
    payload = {"address": address, "latitude": str(latitude), "longitude": str(longitude),
               "origin": list(origin()), "distance": distance, "fee": fee}
    return {"distance_m": distance, "delivery_fee": fee,
            "shipping_quote": signing.dumps(payload, salt="delivery-quote", compress=True)}


def verify_quote(token, address):
    try:
        quote = signing.loads(token, salt="delivery-quote", max_age=900)
    except signing.BadSignature as exc:
        raise ShippingError("El cálculo del envío venció o no es válido. Volvé a calcularlo.") from exc
    if quote["address"] != address or quote["origin"] != list(origin()):
        raise ShippingError("La dirección o la ubicación del local cambió. Volvé a calcular el envío.")
    distance, fee = calculate(quote["latitude"], quote["longitude"])
    if fee != quote["fee"]:
        raise ShippingError("La tarifa cambió. Volvé a calcular el envío.")
    return quote, distance, fee
