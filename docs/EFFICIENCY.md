# Verimlilik ve kullanılabilirlik analizi

Ölçüm: `generic` runtime, tier `high`, 2 açı, aynı soru ("How does Rust's borrow checker enforce lifetimes?"), 2 koşu.
`stats.estTokens` ≈ karakter/4 (kaba), gerçek fatura değil.

## Bulgular ve yapılanlar

| # | Bulgu | Etki | Düzeltme |
|---|---|---|---|
| 1 | Fetch fazı her sayfanın ilk 15 000 karakterini (~3,7k token) çıkarıcıya gönderiyordu; uzun sayfalarda konuyla ilgisiz baş kısım | token + isabet | `core/textutil.excerpt`: soruya en çok uyan paragraflar (sıra korunur), `DR_EXCERPT_CHARS` (6000). Alıntı doğrulaması hâlâ tam metinde |
| 2 | Source seçimi açı açı doluyordu; max_fetch dolunca son açılar hiç kaynak alamıyordu | kapsam, çeşitlilik | Round-robin seçim (her açının en iyisi önce) |
| 3 | Tek bir site tüm kaynakları doldurabiliyordu | bağımsız kaynak çeşitliliği | `DR_MAX_PER_DOMAIN` (varsayılan 2) |
| 4 | Aynı iddia birkaç kaynaktan gelince her biri ayrı doğrulanıyordu | verify çağrısı | Jaccard ≥ 0,75 ile tekilleştirme; diğer kaynaklar `alsoIn` |
| 5 | Doğrulayıcı yalnız iddia+alıntıyı görüyordu, sayfa bağlamını değil ("emin değilsen çürüt" kuralı ile haksız çürütme riski) | doğruluk | Alıntının çevresindeki ~700 karakter bağlam, `<untrusted_source>` içinde |
| 6 | Oylar hep tam sayıda çalışıyordu | verify çağrısı | V < 2R iken R oy aynı yöndeyse kalan oylayıcılar çalıştırılmıyor (sonuç aynı, 3 oylu testle her kombinasyon doğrulandı). `high` tier (V=2,R=2) zaten asgari |
| 7 | Aynı sayfa/arama tekrar tekrar ağdan çekiliyordu | süre, ağ | `core/cache.py` disk önbelleği (`~/.cache/deep-dive`, TTL 6 sa, `DR_CACHE=0` ile kapalı); başarısızlıklar önbelleğe alınmaz |
| 8 | Maliyet görünmüyordu | görünürlük | `stats.estTokens {in,out}` |

## Ölçüm (aynı soru)
- Önce: 37 ajan çağrısı. Sonra: 35 (koşu 1) / 37 (koşu 2); asıl kazanç çağrı sayısında değil, çağrı başına token'da (fetch girdisi sayfa başına ≤ ~1,5k token).
- Giriş ≈ 27–29k token, çıkış ≈ 9k token / koşu (11 kaynak, 12 doğrulanan iddia, 8–9 bulgu). ~26 sn duvar saati.
- Süre baskın olarak LLM çağrıları (Fetch ~8 sn, Verify ~9,5 sn); önbellek yalnız ağ kısmını (Search ~2–3 sn) kısaltır.

## Hâlâ açık
- Tier seçimi elle; "soru zorluğuna göre otomatik tier" yok.
- Doğrulayıcılar hâlâ aynı model: model önyargısı oy birliğiyle düzelmez. Siyasi/yanlı kaynak için `DR_MAX_PER_DOMAIN` ve çok motorlu arama çeşitlilik sağlar ama taraflılık garantisi vermez.
- Alan adı izin/yasak listesi (`DR_SEARCH_DOMAINS`) ve "en az N farklı alan adı" şartı yok.
