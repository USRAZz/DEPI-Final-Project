# PaddleOCR failure review

Source: `eval/results/ocr_paddleocr_all_header_items_experimental_rescored.csv`. This report is generated from OCR output and manifest labels; it does not change invoice PDFs or OCR text.

Similarity is a review hint, not proof of a correction. High scores usually mean the recognizer produced a close typo or split text; low scores need a visual review. Keep the original OCR text alongside any later suggested field value.

Lexicon suggestions use the synthetic fixture vocabulary as a catalog and are printed only when the expected term ranks first with a score of at least 0.78 and an 0.08 margin. This is an assistive synthetic-data review, not a raw-OCR score or a general vendor/product catalog.

Invoices with at least one missed field: 33.

## INV-002

Language: `ar`; quality: `baseline`; layout: `1`; dataset: `original`.

- **vendor** — expected `مؤسسة الأفق المكتبي`; closest OCR: `مؤسسة ة الأفق المكتبي` (0.97). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `مؤسسة الأفق المكتبي` (0.97, margin 0.38); verify against the PDF before applying.

## INV-008

Language: `ar`; quality: `baseline`; layout: `2`; dataset: `original`.

- **vendor** — expected `مكتبة الصفوة`; closest OCR: `مكتبة ال الصفوة` (0.92). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `مكتبة الصفوة` (0.92, margin 0.32); verify against the PDF before applying.

## INV-012

Language: `ar`; quality: `baseline`; layout: `1`; dataset: `original`.

- **vendor** — expected `مؤسسة الأفق المكتبي`; closest OCR: `مؤسسة ة الأفق المكتبي` (0.97). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `مؤسسة الأفق المكتبي` (0.97, margin 0.38); verify against the PDF before applying.

## INV-018

Language: `ar`; quality: `baseline`; layout: `2`; dataset: `original`.

- **vendor** — expected `النور للصيانة`; closest OCR: `النور ل للصيانة` (0.96). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `النور للصيانة` (0.96, margin 0.31); verify against the PDF before applying.

## STRESS-001

Language: `ar`; quality: `clean`; layout: `0`; dataset: `varied-1`.

- **line_1_description** — expected `ورق تصوير A4`; closest OCR: `ورق لصوير` (0.78). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-003

Language: `mixed`; quality: `hard`; layout: `0`; dataset: `varied-1`.

- **tax** — expected `1,521.80`; closest OCR: `1,521.B0 EGP` (0.67). weak read: needs image/layout-specific review.
- **line_2_description** — expected `Transport service`; closest OCR: `clan/ Transport senvice` (0.83). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `Office supplies`; closest OCR: `e cdyl/Office suppies` (0.81). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `Printer toner`; closest OCR: `_/Pintertoner` (0.96). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-004

Language: `ar`; quality: `moderate`; layout: `1`; dataset: `varied-1`.

- **line_2_description** — expected `مواد تعبئة`; closest OCR: `مواد دبكة` (0.71). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `ورق تصوير A4`; closest OCR: `ورق لصوير 4م` (0.80). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-005

Language: `en`; quality: `hard`; layout: `1`; dataset: `varied-1`.

- **tax** — expected `655.20`; closest OCR: `665.20 EGP` (0.62). weak read: needs image/layout-specific review.

## STRESS-007

Language: `ar`; quality: `hard`; layout: `2`; dataset: `varied-1`.

- **line_1_description** — expected `أدوات مكتبية`; closest OCR: `أوات مكية` (0.84). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `حبر طابعة`; closest OCR: `حر طبعة` (0.86). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `خدمة صيانة`; closest OCR: `خمة صيانة` (0.94). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `خدمة صيانة` (0.94, margin 0.08); verify against the PDF before applying.
- **line_4_description** — expected `مواد تعبئة`; closest OCR: `مواد تجينة` (0.67). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-013

Language: `ar`; quality: `moderate`; layout: `4`; dataset: `varied-1`.

- **line_1_description** — expected `معدات شبكات`; closest OCR: `ممدات شبكات` (0.90). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `خدمات استشارية`; closest OCR: `خدمات اسلشارية` (0.92). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-014

Language: `en`; quality: `hard`; layout: `4`; dataset: `varied-1`.

- **line_1_description** — expected `Packaging materials`; closest OCR: `Packaging matenais` (0.86). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `Packaging materials` (0.86, margin 0.21); verify against the PDF before applying.

## STRESS-016

Language: `ar`; quality: `hard`; layout: `5`; dataset: `varied-1`.

- **line_1_description** — expected `ورق تصوير A4`; closest OCR: `وري سور خد` (0.44). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `مياه شرب (عبوات)`; closest OCR: `ميد ترن إعوات` (0.61). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `معدات شبكات`; closest OCR: `مندت قكت` (0.59). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-021

Language: `mixed`; quality: `hard`; layout: `6`; dataset: `varied-1`.

- **line_1_description** — expected `Network equipment`; closest OCR: `/ Netwark equipment` (0.94). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-022

Language: `ar`; quality: `moderate`; layout: `7`; dataset: `varied-1`.

- **line_4_description** — expected `مواد تعبئة`; closest OCR: `مواد تعبنة` (0.89). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_5_description** — expected `ورق تصوير A4`; closest OCR: `ورق تصوير` (0.89). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-025

Language: `ar`; quality: `hard`; layout: `8`; dataset: `varied-1`.

- **line_1_description** — expected `قطع غيار`; closest OCR: `قع` (0.44). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `خدمات نقل`; closest OCR: `ات بل` (0.50). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS-028

Language: `ar`; quality: `clean`; layout: `9`; dataset: `varied-1`.

- **line_1_description** — expected `معدات شبكات`; closest OCR: `محدات شكات` (0.84). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `معدات شبكات` (0.84, margin 0.32); verify against the PDF before applying.

## STRESS-030

Language: `mixed`; quality: `hard`; layout: `9`; dataset: `varied-1`.

- **line_1_description** — expected `Office supplies`; closest OCR: `d/orie supples` (0.77). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `Printer toner`; closest OCR: `W  / Prnter toner` (0.92). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `Maintenance service`; closest OCR: `Ale ta/ Maintenance senvice` (0.83). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `Packaging materials`; closest OCR: `/Packaging matenals` (0.91). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_line_total_egp** — expected `630.00`; closest OCR: `630:00` (1.00). near-read: likely digit or separator confusion.

## STRESS2-003

Language: `mixed`; quality: `hard`; layout: `0`; dataset: `varied-2`.

- **line_1_description** — expected `Safety equipment`; closest OCR: `ula/ Safety equapment` (0.85). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `Delivery service`; closest OCR: `d Aas/Dehvery senvice` (0.73). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `Technical training`; closest OCR: `uus/ Technical raining` (0.89). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `Installation service`; closest OCR: `/ Instatation service` (0.92). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS2-004

Language: `ar`; quality: `moderate`; layout: `1`; dataset: `varied-2`.

- **line_1_description** — expected `اشتراك برمجي`; closest OCR: `اشراك برمجي` (0.95). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `مستلزمات تغليف`; closest OCR: `مسلزمات نغليف` (0.88). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS2-005

Language: `en`; quality: `hard`; layout: `1`; dataset: `varied-2`.

- **line_1_description** — expected `Delivery service`; closest OCR: `Delvery senvce` (0.86). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `Delivery service` (0.86, margin 0.15); verify against the PDF before applying.

## STRESS2-007

Language: `ar`; quality: `hard`; layout: `2`; dataset: `varied-2`.

- **line_1_description** — expected `تدريب فني`; closest OCR: `تريب في` (0.86). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `خدمة تركيب`; closest OCR: `خمه ركيب` (0.88). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `اشتراك برمجي`; closest OCR: `شرك ومي` (0.59). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `مستلزمات تغليف`; closest OCR: `ستزمات عليف` (0.78). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS2-013

Language: `ar`; quality: `moderate`; layout: `4`; dataset: `varied-2`.

- **line_1_description** — expected `قطع كهربائية`; closest OCR: `فلع كهرباكية` (0.73). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `خدمة معايرة`; closest OCR: `خدمة معابرة` (0.90). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `خدمة معايرة` (0.90, margin 0.17); verify against the PDF before applying.

## STRESS2-014

Language: `en`; quality: `hard`; layout: `4`; dataset: `varied-2`.

- **line_1_description** — expected `Wrapping supplies`; closest OCR: `Whapping supplies` (0.94). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `Wrapping supplies` (0.94, margin 0.23); verify against the PDF before applying.

## STRESS2-016

Language: `ar`; quality: `hard`; layout: `5`; dataset: `varied-2`.

- **line_1_description** — expected `أحبار وأدوات طباعة`; closest OCR: `لسار ولتات مطاعة` (0.60). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `مواد تنظيف`; closest OCR: `مواد لنليف` (0.78). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `قطع كهربائية`; closest OCR: `فاتورة ضريبية` (0.43). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS2-025

Language: `ar`; quality: `hard`; layout: `8`; dataset: `varied-2`.

- **line_1_description** — expected `معدات سلامة`; closest OCR: `مسات صالمه` (0.63). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `خدمة توصيل`; closest OCR: `عقة قوصيل` (0.59). weak read: needs image/layout-specific review.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS2-028

Language: `ar`; quality: `clean`; layout: `9`; dataset: `varied-2`.

- **line_1_description** — expected `قطع كهربائية`; closest OCR: `فطع كهربائبة` (0.82). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `قطع كهربائية` (0.82, margin 0.25); verify against the PDF before applying.

## STRESS2-030

Language: `mixed`; quality: `hard`; layout: `9`; dataset: `varied-2`.

- **line_1_description** — expected `Technical training`; closest OCR: `/ Techrical traning` (0.91). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_2_description** — expected `Installation service`; closest OCR: `/Instalaon servie` (0.88). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `Software subscription`; closest OCR: `d/ Soffware subsicription` (0.90). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `Wrapping supplies`; closest OCR: `L chjla/Wrapping supples` (0.81). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_5_description** — expected `Ink and printing supplies`; closest OCR: `ink and prring supples` (0.88). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_5_line_total_egp** — expected `1,560.00`; closest OCR: `1,450.00` (0.83). weak read: needs image/layout-specific review.

## STRESS3-001

Language: `ar`; quality: `clean`; layout: `0`; dataset: `clear-20`.

- **line_2_description** — expected `صيانة دورية`; closest OCR: `صيبانة دورية` (0.95). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS3-007

Language: `ar`; quality: `clean`; layout: `6`; dataset: `clear-20`.

- **vendor** — expected `مركز الإتقان للصيانة`; closest OCR: `مركز ٤ إتقان للصيائة` (0.86). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `مركز الإتقان للصيانة` (0.86, margin 0.19); verify against the PDF before applying.

## STRESS3-010

Language: `ar`; quality: `clean`; layout: `9`; dataset: `clear-20`.

- **line_1_description** — expected `خدمة تركيب أجهزة`; closest OCR: `خدمة تركبب أجهزة` (0.93). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS3-016

Language: `ar`; quality: `clean`; layout: `5`; dataset: `clear-20`.

- **line_2_description** — expected `صيانة دورية`; closest OCR: `صديانة دورية` (0.95). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_3_description** — expected `تراخيص برامج`; closest OCR: `تراخبص برامج` (0.91). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.
- **line_4_description** — expected `معدات وقاية`; closest OCR: `محدات وفاية` (0.80). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

## STRESS3-018

Language: `mixed`; quality: `clean`; layout: `7`; dataset: `clear-20`.

- **vendor** — expected `Al Marsa Services`; closest OCR: `/ AI Mars Services` (0.90). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: `Al Marsa Services` (0.90, margin 0.17); verify against the PDF before applying.

## STRESS3-019

Language: `ar`; quality: `clean`; layout: `8`; dataset: `clear-20`.

- **line_2_description** — expected `معدات وقاية`; closest OCR: `معدات وقابة` (0.90). near-read: likely character confusion or a split word.
  - Synthetic-catalog suggestion: no safe match; review the source image.

Total missed fields: 67.
