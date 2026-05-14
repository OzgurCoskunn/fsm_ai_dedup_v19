# FSM AI Dedup (Odoo 19)

Partner duplikasyon engelleme modulu — OpenRouter uzerinden LLM ile adres karsilastirma.

Bu surum **Odoo 19** uyumlu, `fsm_api` modulune bagimlidir. Postman'den
`/api/v1/fsm/workorders`, `/api/v1/fsm/saleorders/create` ve
`/api/v1/fsm/saleorders/approve/<orderId>` endpointlerine istek atildiginda
otomatik olarak normalize + AI fallback ile partner eslestirme yapilir.

## Ozellikler
- Telefon, VKN, e-posta, isim normalize fonksiyonlari
- OpenRouter uzerinden LLM ile semantik adres karsilastirma
- Settings ekraninda API key + model + threshold
- Manuel test wizard'i (AI Dedup > Manuel Test)
- Karar loglari (AI Dedup > Loglar)

## v16 ile farklari
- View XML'leri v19 syntax'i (block/setting, `invisible="..."`, `<list>` tag)
- Manifest version: `19.0.1.0.0`
- Manuel test wizard'i da eklendi (otomatik fallback'in yaninda)

## Bagimliliklar
- Python: `requests`
- Odoo: `base`, `base_setup`, `contacts`, `fsm_api`

## Kurulum
1. Modul klasorunu Odoo addons path'ine kopyala
2. Apps > Update Apps List
3. "FSM AI Dedup (v19)" modulunu Install et
4. Settings > General Settings > FSM AI Dedup bolumunden:
   - AI Dedup Etkin = ON
   - OpenRouter API Key gir
   - Modeli sec (varsayilan: openai/gpt-4o-mini)
   - "OpenRouter Baglantisini Test Et" butonuna bas
5. AI Dedup > Manuel Test menusunden bir partneri test et

## Postman ile test
Settings'ten AI Dedup'i etkinlestirip API key girdikten sonra:

```
POST /api/v1/fsm/workorders
POST /api/v1/fsm/saleorders/create
POST /api/v1/fsm/saleorders/approve/<orderId>
```

endpointlerine istek attiginda normalize + AI fallback otomatik calisir.
Tum kararlar **AI Dedup > Loglar** menusunde gozukur.
