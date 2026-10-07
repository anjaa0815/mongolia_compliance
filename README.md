# Mongolia Compliance

ERPNext-ийг Монголын нөхцөлд нутагшуулах Frappe апп. ERPNext-ийн үндсэн кодыг өөрчлөхгүй, бүх нэмэлт энэ апп дотор hooks, custom field, суулгах скриптээр хийгдэнэ.

## Модулиуд

| Модуль | Агуулга |
| --- | --- |
| Mongolia Accounting | Монгол дансны төлөвлөгөө, НӨАТ 10% / 0% / чөлөөлөгдсөн татварын загвар, суутган тооцох татварын ангилал, СТ-1, СТ-2 тайлангийн загвар, НӨАТ-ын тайлан |
| E-Barimt | И-Баримт 3.0 (PosAPI) холболт, ДДТД / QR / сугалааны дугаар, буцаалт ба цуцлалт, ТТД лавлах, QR-тай баримтын хэвлэх загвар |

Орчуулга `mongolia_compliance/locale/mn.po` дотор байна. ERPNext-ийн орчуулаагүй мөрүүдийг нөхөж, буруу орчуулсан нэр томьёог (Stock, Item, Quotation, Lead гэх мэт) дарж бичнэ.

## Суулгах

```bash
cd frappe-bench
bench get-app <энэ аппын git хаяг>
bench --site <site> install-app mongolia_compliance
bench --site <site> migrate
```

Апп суулгасны дараа:

1. Улс нь Mongolia шинэ компани үүсгэхэд "Use Mongolian Chart of Accounts" сонгогдсон бол сонгосон дансны төлөвлөгөө Монгол төлөвлөгөөгөөр солигдож, НӨАТ болон суутгалын загварууд үүснэ. Гүйлгээгүй хуучин компанид `mongolia_compliance.mongolia_accounting.setup.install_mongolian_chart` дуудаж суулгаж болно.
2. **E-Barimt Settings** дээр компани тус бүрийн PosAPI хаяг, ТТД, салбар, дүүргийн код, НӨАТ ба НХАТ-ын дансыг тохируулаад "Test Connection" дарна.
3. Барааны карт дээр БҮНА код, шаардлагатай бол И-Баримтын татварын төрлийг бөглөнө.

## Бүтэц

```
mongolia_compliance/
├── hooks.py              # doc_events, doctype_js, scheduler, jinja
├── install.py            # after_install / after_migrate: custom field, тайлангийн загвар
├── locale/mn.po          # монгол орчуулга
├── public/js/            # Customer, Sales/POS Invoice формын нэмэлт
├── mongolia_accounting/  # дансны төлөвлөгөө, татвар, тайлан
└── e_barimt/             # И-Баримт
```

Шинэ модуль (жишээ нь Mongolia Payroll, Mongolia Banking) нэмэхдээ `modules.txt`-д нэрийг нь бичиж, ижил нэртэй хавтас үүсгээд, hooks-оо `hooks.py`-д нэмнэ.

## Анхааруулга

- И-Баримтын PosAPI 3.0 болон татвар төлөгч лавлах API-г амьд орчинд туршаагүй. Эхлээд туршилтын PosAPI дээр шалгана уу.
- Дансны төлөвлөгөө, суутгалын хувь хэмжээг нягтлан бодогчоор хянуулна уу.

## Лиценз

GPL-3.0
