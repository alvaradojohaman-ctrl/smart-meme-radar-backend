"""Exact numerical translation of score/risk in the supplied v0.4D ZIP.
No training, optimization or Smart Money features.
"""
import math

def num(value):
    try:
        n = float(value or 0)
        return n if math.isfinite(n) else 0.0
    except (ValueError, TypeError):
        return 0.0

def clamp(x, a=0, b=1):
    return max(a, min(b, x))

def inputs(p):
    return (num((p.get('liquidity') or {}).get('usd')), num(p.get('marketCap') or p.get('fdv')),
            num(((p.get('txns') or {}).get('h1') or {}).get('buys')),
            num(((p.get('txns') or {}).get('h1') or {}).get('sells')),
            num((p.get('priceChange') or {}).get('h1')))

def score(p):
    l,m,b,s,c = inputs(p)
    v = num((p.get('volume') or {}).get('h24'))
    r = clamp(l/50000)*25 + clamp(v/100000)*20 + clamp((b+s)/100)*15
    r += clamp(b/(b+s))*15 if b+s else 0
    r += clamp((c+10)/30)*10
    r += clamp(l/m*5)*15 if m and l else 0
    return math.floor(clamp(r,0,100)+0.5)

def risk(p):
    l,m,b,s,c = inputs(p)
    ratio = l/m if m>0 else 0
    points, reasons, hard = 0, [], False
    if l<10000: points+=40; reasons.append('liquidez < $10K'); hard=True
    elif l<25000: points+=20; reasons.append('liquidez baja')
    if m>0 and ratio<.03: points+=30; reasons.append('liq/MC < 3%'); hard=True
    elif m>0 and ratio<.07: points+=15; reasons.append('liq/MC baja')
    if c<=-35: points+=35; reasons.append('caída 1h extrema'); hard=True
    elif c<=-20: points+=20; reasons.append('caída 1h fuerte')
    if b+s>=20 and s>b*2: points+=30; reasons.append('ventas >2× compras'); hard=True
    elif b+s>=20 and s>b*1.4: points+=15; reasons.append('presión vendedora')
    if abs(c)>=80: points+=15; reasons.append('volatilidad extrema')
    points = math.floor(clamp(points,0,100)+.5)
    return dict(points=points, blocked=hard or points>=60, reasons=reasons or ['sin alerta crítica'])

def snapshot(p):
    l,m,b,s,c = inputs(p)
    return dict(liq=l, mc=m, vol=num((p.get('volume') or {}).get('h24')), buys=b, sells=s, change1h=c)
