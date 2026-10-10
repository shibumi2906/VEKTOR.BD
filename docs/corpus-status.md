# Состояние нормативного корпуса C01

Дата: 10.10.2026. Политика: **один полный подтверждённый действующий текст каждого документа; отдельные поправки и предыдущие варианты удалены.**

После явного поручения пользователя удалены 208 PDF из PostgreSQL, рабочей папки и raw-data volume: 180 публикаций поправок, 9 исправлений, 18 законодательных публикаций и дубль стандарта 21.1. Осталось 15 PDF, 205 страниц. Проектные договоры не затронуты. Архив старых PDF не создан. Audit содержит факт очистки, без текстов удалённых публикаций.

**Полные актуальные редакции 16 законов пока не получены.** Исходные публикации не подменяют сводные тексты. Пользователь не имеет доступа к Нево/Такдин. Кнессет предоставляет исходные публикации и историю поправок; доступ к карточке оценщиков из локальной среды вернул HTTP 247. Найденные сводные копии не подтверждены актуальными на 09.10.2026.

Реестр: PostgreSQL schema registry; manifest data/corpus-manifest.json. Все 15 оставшихся public документов обработаны и индексированы (950 active chunks). Дополнительно индексированы два частных договора (2713 chunks) и один закрытый synthetic OCR fixture (1 chunk); эти документы не меняют правовую комплектность. Стандарт gov_standard21 подтверждён как verified/current/in_force; у остальных документов сохранены прежние статусы manual_review/unknown. Рекомендации, шаблоны и решение по этике не объявлены законами или действующими обязательными нормами.

## Сохранённые документы

| Документ | Тип | Источник |
|---|---|---|
| תקן 21.1, 2022 — standard | standard | [оригинал](https://www.gov.il/BlobFolder/policy/standard_21/he/hithadshut_ironit_documents_standard_21_1.pdf) |
| Minimum entrepreneurial profit — December 2025 | official_guidance | [оригинал](https://www.gov.il/BlobFolder/dynamiccollectorresultitem/assessor-standardization-db-21/he/land_assessor_shameim_profit-rate-25.pdf) |
| Organizer fees — February 2026 | official_guidance | [оригинал](https://www.gov.il/BlobFolder/dynamiccollectorresultitem/25-02-2026/he/25-02-2026.pdf) |
| התנהלות מול עורכי דין המייצגים בעלי דירות בהתחדשות עירונית | official_guidance | [оригинал](https://www.gov.il/BlobFolder/policy/hitnahalut_mul_orchey_din_hitchadshut_ironit/he/hithadshut_ironit_documents_hitnahalut_orchey_din_hitchadshut_ironit.pdf) |
| התנהלות בעלי דירות מול מארגנים בהתחדשות עירונית | official_guidance | [оригинал](https://www.gov.il/BlobFolder/policy/urban-renewal-owner-organizer-interaction/he/hithadshut_ironit_documents_urban-renewal-owner-organizer-interaction.pdf) |
| שכר מארגנים בפרויקטים של התחדשות עירונית — 22.08.2024 | official_guidance | [оригинал](https://www.gov.il/BlobFolder/policy/urban-renewal-owner-organizer-interaction/he/hithadshut_ironit_documents_urban_renewal_project_organizer_salary.pdf) |
| תכנית עבודה מומלצת לנציגות | official_guidance | [оригинал](https://www.gov.il/BlobFolder/guide/ekronot_netzigut_dayarim/he/hithadshut_ironit_documents_ekronot_netzigut_dayarim_nispach.pdf) |
| כתב הסמכה של הנציגות מטעם הרשות הממשלתית להתחדשות עירונית | model_form | [оригинал](https://www.minhelet-holon.co.il/wp-content/uploads/2019/09/%D7%9B%D7%AA%D7%91-%D7%94%D7%A1%D7%9E%D7%9B%D7%94-%D7%A9%D7%9C-%D7%94%D7%A0%D7%A6%D7%99%D7%92%D7%95%D7%AA.pdf) |
| עקרונות בניית נציגות דיירים מטעם הרשות הממשלתית להתחדשות עירונית | official_guidance | [оригинал](https://www.gov.il/BlobFolder/guide/ekronot_netzigut_dayarim/he/hithadshut_ironit_documents_ekronot_netzigut_dayarim_full_text.pdf) |
| מדריך להסכם פינוי בינוי מטעם הרשות הממשלתית להתחדשות עירונית | official_guidance | [оригинал](https://www.gov.il/BlobFolder/generalpage/heskem-pinuy-binuy-ledugma/he/hithadshut_ironit_documents_madrich_heskem_pinuy_binuy.pdf) |
| הסכם לדוגמה בין בעלי הדירות ליזם לעסקת פינוי בינוי - מטעם הרשות הממשלתית להתחדשות עירונית | model_agreement | [оригинал](https://www.minhelet-holon.co.il/wp-content/uploads/2022/01/%D7%94%D7%A1%D7%9B%D7%9D-%D7%9C%D7%93%D7%95%D7%92%D7%9E%D7%90-%D7%91%D7%99%D7%9F-%D7%99%D7%96%D7%9D-%D7%9C%D7%91%D7%A2%D7%9C%D7%99%D7%99-%D7%93%D7%99%D7%A8%D7%95%D7%AA-%D7%91%D7%A2%D7%A1%D7%A7%D7%AA-%D7%A4%D7%99%D7%A0%D7%95%D7%99-%D7%91%D7%99%D7%A0%D7%95%D7%99.pdf) |
| תקנות פינוי בינוי - כינוס דיירים ועיקרי הצעה (התשפ"ב 2022) | regulation_gazette | [оригинал](https://www.minhelet-holon.co.il/wp-content/uploads/2022/06/%D7%AA%D7%A7%D7%A0%D7%95%D7%AA-%D7%A4%D7%99%D7%A0%D7%95%D7%99-%D7%91%D7%99%D7%A0%D7%95%D7%99-%D7%9B%D7%99%D7%A0%D7%95%D7%A1-%D7%95%D7%9E%D7%A1%D7%9E%D7%9A-%D7%A2%D7%99%D7%A7%D7%A8%D7%99-%D7%94%D7%A6%D7%A2%D7%94-%D7%A7%D7%95%D7%91%D7%A5-%D7%94%D7%AA%D7%A7%D7%A0%D7%95%D7%AA-9992.pdf) |
| הסכם למתן שירותים משפטיים — הסכם לדוגמה | model_agreement | [оригинал](https://cramim-pt.co.il/wp-content/uploads/2023/03/%D7%94%D7%A1%D7%9B%D7%9D-%D7%9E%D7%AA%D7%9F-%D7%9C%D7%A9%D7%99%D7%A8%D7%95%D7%AA%D7%99%D7%9D-%D7%9E%D7%A9%D7%A4%D7%98%D7%99%D7%99%D7%9D.pdf) |
| תקנות פינוי ובינוי — תשלום בשל ביטול עסקת התחדשות עירונית — קובץ התקנות 11779 | regulation_gazette | [оригинал](https://minhelet-j.org.il/wp-content/uploads/2025/06/%D7%A7%D7%95%D7%91%D7%A5-%D7%AA%D7%A7%D7%A0%D7%95%D7%AA-11779-%D7%AA%D7%A9%D7%9C%D7%95%D7%9D-%D7%91%D7%A9%D7%9C-%D7%91%D7%99%D7%98%D7%95%D7%9C-%D7%A2%D7%A1%D7%A7%D7%AA-%D7%94%D7%AA%D7%97%D7%93%D7%A9%D7%95%D7%AA-%D7%A2%D7%99%D7%A8%D7%95%D7%A0%D7%99%D7%AA.pdf) |
| התנהלות עורכי דין בפרויקט התחדשות עירונית — את/67/21 | ethics_decision | [оригинал](https://www.nzc.org.il/uploads/n/1728989690.3437.pdf) |

## Отсутствующие полные документы

| Документ | Требуемая версия |
|---|---|
| תקנות פינוי ובינוי (מינוי שמאי פינוי ובינוי וסדרי דין), 2012 | Полный официальный актуальный текст |
| תקנות פינוי ובינוי (כללים לקביעת שכרו של שמאי פינוי ובינוי), 2011 | Полный официальный актуальный текст |
| חוק פינוי ובינוי (עידוד מיזמי פינוי ובינוי), 2006 | Полная действующая сводная редакция |
| חוק הרשות הממשלתית להתחדשות עירונית, 2016 | Полная действующая сводная редакция |
| חוק התחדשות עירונית (הסכמים לארגון עסקאות), 2017 | Полная действующая сводная редакция |
| חוק המקרקעין (חיזוק בתים משותפים מפני רעידות אדמה), 2008 | Полная действующая сводная редакция |
| חוק המקרקעין, 1969 | Полная действующая сводная редакция |
| חוק התכנון והבניה, 1965 | Полная действующая сводная редакция |
| חוק מיסוי מקרקעין (שבח ורכישה), 1963 | Полная действующая сводная редакция |
| חוק המכר (דירות), 1973 | Полная действующая сводная редакция |
| חוק המכר (דירות) (הבטחת השקעות של רוכשי דירות), 1974 | Полная действующая сводная редакция |
| חוק זכויות הדייר בדיור הציבורי, 1998 | Полная действующая сводная редакция |
| חוק שמאי מקרקעין, 2001 | Полная действующая сводная редакция |
| חוק החוזים (חלק כללי), 1973 | Полная действующая сводная редакция |
| חוק החוזים (תרופות בשל הפרת חוזה), 1970 | Полная действующая сводная редакция |
| חוק לקידום הבנייה במתחמים מועדפים (הוראת שעה), 2014 | Полная действующая сводная редакция |
| חוק שוויון זכויות לאנשים עם מוגבלות, 1998 | Полная действующая сводная редакция |
| חוק שיקום נזקי מלחמה בדרך של התחדשות עירונית, 2026 | Полная действующая сводная редакция |

При повторном download/import запрещены исторические законодательные типы. Новый consolidated_law требует verified/current/in_force и даты проверки сводной редакции. Юридическая актуальность оставшихся рекомендаций и актов требует отдельной проверки, прежде чем они войдут в current_norms.

Источники сведений о структуре официального реестра: [Кнессет — описание](https://main.knesset.gov.il/Activity/Legislation/Laws/pages/lawaboutsite.aspx?g=7), [Кнессет — FAQ](https://main.knesset.gov.il/apps/legislation/main/info/pages/faq).
