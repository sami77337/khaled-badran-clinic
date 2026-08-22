"""Local metadata for the progressively enhanced public-booking phone selector."""


# Row fields: ISO code, dial code, English name, Arabic name, domestic-format
# example, and a known domestic prefix that is safe to strip. The public
# ``example`` value is derived below as a national subscriber number, because
# the selector renders the international dial code separately.
_COUNTRY_ROWS = """
JO|+962|Jordan|الأردن|079XXXXXXX|0
SA|+966|Saudi Arabia|السعودية|05XXXXXXXX|0
AE|+971|United Arab Emirates|الإمارات العربية المتحدة|05XXXXXXXX|0
PS|+970|Palestine|فلسطين|05X XXX XXXX|0
BH|+973|Bahrain|البحرين|3XXX XXXX|
EG|+20|Egypt|مصر|01X XXXX XXXX|0
IQ|+964|Iraq|العراق|07XX XXX XXXX|0
KW|+965|Kuwait|الكويت|5XXX XXXX|
LB|+961|Lebanon|لبنان|03 XXX XXX|0
OM|+968|Oman|عُمان|9XXX XXXX|
QA|+974|Qatar|قطر|3XXX XXXX|
SY|+963|Syria|سوريا|09XX XXX XXX|0
YE|+967|Yemen|اليمن|7XX XXX XXX|
DZ|+213|Algeria|الجزائر|05XX XX XX XX|0
LY|+218|Libya|ليبيا|09X XXX XXXX|0
MA|+212|Morocco|المغرب|06XX XX XX XX|0
SD|+249|Sudan|السودان|09X XXX XXXX|0
SO|+252|Somalia|الصومال|6X XXX XXXX|
TN|+216|Tunisia|تونس|2X XXX XXX|
AD|+376|Andorra|أندورا|3XX XXX|
AF|+93|Afghanistan|أفغانستان|07X XXX XXXX|0
AG|+1|Antigua and Barbuda|أنتيغوا وباربودا|268 464 1234|
AI|+1|Anguilla|أنغويلا|264 235 1234|
AL|+355|Albania|ألبانيا|06X XXX XXXX|0
AM|+374|Armenia|أرمينيا|0XX XXX XXX|0
AO|+244|Angola|أنغولا|9XX XXX XXX|
AQ|+672|Antarctica|القارة القطبية الجنوبية|1X XXX|
AR|+54|Argentina|الأرجنتين|9 11 XXXX XXXX|
AS|+1|American Samoa|ساموا الأمريكية|684 733 1234|
AT|+43|Austria|النمسا|06XX XXX XXXX|0
AU|+61|Australia|أستراليا|04XX XXX XXX|0
AW|+297|Aruba|أروبا|5XX XXXX|
AX|+358|Åland Islands|جزر آلاند|04X XXX XXXX|0
AZ|+994|Azerbaijan|أذربيجان|050 XXX XX XX|0
BA|+387|Bosnia and Herzegovina|البوسنة والهرسك|06X XXX XXX|0
BB|+1|Barbados|بربادوس|246 250 1234|
BD|+880|Bangladesh|بنغلاديش|01X XXXXXXXX|0
BE|+32|Belgium|بلجيكا|04XX XX XX XX|0
BF|+226|Burkina Faso|بوركينا فاسو|70 XX XX XX|
BG|+359|Bulgaria|بلغاريا|08XX XXX XXX|0
BI|+257|Burundi|بوروندي|7X XX XX XX|
BJ|+229|Benin|بنين|01 XX XX XX XX|
BL|+590|Saint Barthélemy|سان بارتليمي|0690 XX XX XX|0
BM|+1|Bermuda|برمودا|441 370 1234|
BN|+673|Brunei|بروناي|7XX XXXX|
BO|+591|Bolivia|بوليفيا|7XXXXXXX|
BQ|+599|Caribbean Netherlands|هولندا الكاريبية|7XX XXXX|
BR|+55|Brazil|البرازيل|11 9XXXX XXXX|
BS|+1|Bahamas|جزر البهاما|242 359 1234|
BT|+975|Bhutan|بوتان|17 XX XX XX|
BW|+267|Botswana|بوتسوانا|7X XXX XXX|
BY|+375|Belarus|بيلاروس|8 029 XXX XX XX|80
BZ|+501|Belize|بليز|6XX XXXX|
CA|+1|Canada|كندا|416 555 0123|
CC|+61|Cocos (Keeling) Islands|جزر كوكوس (كيلينغ)|04XX XXX XXX|0
CD|+243|Democratic Republic of the Congo|جمهورية الكونغو الديمقراطية|09XX XXX XXX|0
CF|+236|Central African Republic|جمهورية أفريقيا الوسطى|70 XX XX XX|
CG|+242|Republic of the Congo|جمهورية الكونغو|06 XXX XXXX|0
CH|+41|Switzerland|سويسرا|07X XXX XX XX|0
CI|+225|Côte d’Ivoire|ساحل العاج|0X XX XX XX XX|0
CK|+682|Cook Islands|جزر كوك|7X XXX|
CL|+56|Chile|تشيلي|9 XXXX XXXX|
CM|+237|Cameroon|الكاميرون|6 XX XX XX XX|
CN|+86|China|الصين|1XX XXXX XXXX|
CO|+57|Colombia|كولومبيا|3XX XXX XXXX|
CR|+506|Costa Rica|كوستاريكا|8XXX XXXX|
CU|+53|Cuba|كوبا|5 XXX XXXX|
CV|+238|Cabo Verde|الرأس الأخضر|9XX XX XX|
CW|+599|Curaçao|كوراساو|9 XXX XXXX|
CX|+61|Christmas Island|جزيرة كريسماس|04XX XXX XXX|0
CY|+357|Cyprus|قبرص|9X XXX XXX|
CZ|+420|Czechia|التشيك|6XX XXX XXX|
DE|+49|Germany|ألمانيا|015X XXXXXXXX|0
DJ|+253|Djibouti|جيبوتي|77 XX XX XX|
DK|+45|Denmark|الدنمارك|20 XX XX XX|
DM|+1|Dominica|دومينيكا|767 225 1234|
DO|+1|Dominican Republic|جمهورية الدومينيكان|809 234 5678|
EC|+593|Ecuador|الإكوادور|09X XXX XXXX|0
EE|+372|Estonia|إستونيا|5XXX XXXX|
EH|+212|Western Sahara|الصحراء الغربية|06XX XX XX XX|0
ER|+291|Eritrea|إريتريا|07X XXX XXX|0
ES|+34|Spain|إسبانيا|6XX XXX XXX|
ET|+251|Ethiopia|إثيوبيا|09X XXX XXXX|0
FI|+358|Finland|فنلندا|04X XXX XXXX|0
FJ|+679|Fiji|فيجي|7XX XXXX|
FK|+500|Falkland Islands|جزر فوكلاند|5XXXX|
FM|+691|Micronesia|ميكرونيسيا|3XX XXXX|
FO|+298|Faroe Islands|جزر فارو|2XX XXX|
FR|+33|France|فرنسا|06 XX XX XX XX|0
GA|+241|Gabon|الغابون|06 XX XX XX|0
GB|+44|United Kingdom|المملكة المتحدة|07XXX XXXXXX|0
GD|+1|Grenada|غرينادا|473 403 1234|
GE|+995|Georgia|جورجيا|5XX XX XX XX|
GF|+594|French Guiana|غويانا الفرنسية|0694 XX XX XX|0
GG|+44|Guernsey|غيرنزي|07781 XXXXXX|0
GH|+233|Ghana|غانا|02X XXX XXXX|0
GI|+350|Gibraltar|جبل طارق|5XXX XXXX|
GL|+299|Greenland|غرينلاند|22 XX XX|
GM|+220|Gambia|غامبيا|3XX XXXX|
GN|+224|Guinea|غينيا|6XX XX XX XX|
GP|+590|Guadeloupe|غوادلوب|0690 XX XX XX|0
GQ|+240|Equatorial Guinea|غينيا الاستوائية|222 XXX XXX|
GR|+30|Greece|اليونان|69X XXX XXXX|
GS|+500|South Georgia and the South Sandwich Islands|جورجيا الجنوبية وجزر ساندويتش الجنوبية|5XXXX|
GT|+502|Guatemala|غواتيمالا|5XXX XXXX|
GU|+1|Guam|غوام|671 300 1234|
GW|+245|Guinea-Bissau|غينيا بيساو|9XX XXXX|
GY|+592|Guyana|غيانا|6XX XXXX|
HK|+852|Hong Kong|هونغ كونغ|5XXX XXXX|
HN|+504|Honduras|هندوراس|9XXX XXXX|
HR|+385|Croatia|كرواتيا|09X XXX XXXX|0
HT|+509|Haiti|هايتي|3X XX XXXX|
HU|+36|Hungary|المجر|06 20 XXX XXXX|06
ID|+62|Indonesia|إندونيسيا|08XX XXXX XXXX|0
IE|+353|Ireland|أيرلندا|08X XXX XXXX|0
IL|+972|Israel|إسرائيل|05X XXX XXXX|0
IM|+44|Isle of Man|جزيرة مان|07624 XXXXXX|0
IN|+91|India|الهند|9XXXX XXXXX|
IO|+246|British Indian Ocean Territory|إقليم المحيط الهندي البريطاني|380 XXXX|
IR|+98|Iran|إيران|09XX XXX XXXX|0
IS|+354|Iceland|آيسلندا|6XX XXXX|
IT|+39|Italy|إيطاليا|3XX XXX XXXX|
JE|+44|Jersey|جيرزي|07797 XXXXXX|0
JM|+1|Jamaica|جامايكا|876 210 1234|
JP|+81|Japan|اليابان|090 XXXX XXXX|0
KE|+254|Kenya|كينيا|07XX XXX XXX|0
KG|+996|Kyrgyzstan|قيرغيزستان|0700 XXX XXX|0
KH|+855|Cambodia|كمبوديا|09X XXX XXX|0
KI|+686|Kiribati|كيريباتي|7XXX XXXX|
KM|+269|Comoros|جزر القمر|3XX XX XX|
KN|+1|Saint Kitts and Nevis|سانت كيتس ونيفيس|869 765 1234|
KP|+850|North Korea|كوريا الشمالية|0192 XXX XXXX|0
KR|+82|South Korea|كوريا الجنوبية|010 XXXX XXXX|0
KY|+1|Cayman Islands|جزر كايمان|345 323 1234|
KZ|+7|Kazakhstan|كازاخستان|8 701 XXX XX XX|8
LA|+856|Laos|لاوس|020 XX XXX XXX|0
LC|+1|Saint Lucia|سانت لوسيا|758 284 1234|
LI|+423|Liechtenstein|ليختنشتاين|7XX XX XX|
LK|+94|Sri Lanka|سريلانكا|07X XXX XXXX|0
LR|+231|Liberia|ليبيريا|077 XXX XXXX|0
LS|+266|Lesotho|ليسوتو|5XXX XXXX|
LT|+370|Lithuania|ليتوانيا|06XX XXXXX|0
LU|+352|Luxembourg|لوكسمبورغ|6XX XXX XXX|
LV|+371|Latvia|لاتفيا|2XXX XXXX|
MC|+377|Monaco|موناكو|06 XX XX XX XX|0
MD|+373|Moldova|مولدوفا|06XX XX XXX|0
ME|+382|Montenegro|الجبل الأسود|06X XXX XXX|0
MF|+590|Saint Martin|سان مارتن|0690 XX XX XX|0
MG|+261|Madagascar|مدغشقر|032 XX XXX XX|0
MH|+692|Marshall Islands|جزر مارشال|235 XXXX|
MK|+389|North Macedonia|مقدونيا الشمالية|07X XXX XXX|0
ML|+223|Mali|مالي|6X XX XX XX|
MM|+95|Myanmar|ميانمار|09 XXX XXX XXX|0
MN|+976|Mongolia|منغوليا|8XXX XXXX|
MO|+853|Macao|ماكاو|6XXX XXXX|
MP|+1|Northern Mariana Islands|جزر ماريانا الشمالية|670 234 5678|
MQ|+596|Martinique|مارتينيك|0696 XX XX XX|0
MR|+222|Mauritania|موريتانيا|2X XX XX XX|
MS|+1|Montserrat|مونتسرات|664 492 1234|
MT|+356|Malta|مالطا|7XXX XXXX|
MU|+230|Mauritius|موريشيوس|5XXX XXXX|
MV|+960|Maldives|المالديف|7XX XXXX|
MW|+265|Malawi|ملاوي|099X XX XX XX|0
MX|+52|Mexico|المكسيك|55 XXXX XXXX|
MY|+60|Malaysia|ماليزيا|01X XXX XXXX|0
MZ|+258|Mozambique|موزمبيق|8X XXX XXXX|0
NA|+264|Namibia|ناميبيا|081 XXX XXXX|0
NC|+687|New Caledonia|كاليدونيا الجديدة|7X XX XX|
NE|+227|Niger|النيجر|9X XX XX XX|
NF|+672|Norfolk Island|جزيرة نورفولك|3 XXXX|
NG|+234|Nigeria|نيجيريا|08XX XXX XXXX|0
NI|+505|Nicaragua|نيكاراغوا|8XXX XXXX|
NL|+31|Netherlands|هولندا|06 XXXXXXXX|0
NO|+47|Norway|النرويج|4XX XX XXX|
NP|+977|Nepal|نيبال|98X XXX XXXX|
NR|+674|Nauru|ناورو|555 XXXX|
NU|+683|Niue|نيوي|8XXX|
NZ|+64|New Zealand|نيوزيلندا|02X XXX XXXX|0
PA|+507|Panama|بنما|6XXX XXXX|
PE|+51|Peru|بيرو|9XX XXX XXX|
PF|+689|French Polynesia|بولينيزيا الفرنسية|87 XX XX XX|
PG|+675|Papua New Guinea|بابوا غينيا الجديدة|7XXX XXXX|
PH|+63|Philippines|الفلبين|09XX XXX XXXX|0
PK|+92|Pakistan|باكستان|03XX XXXXXXX|0
PL|+48|Poland|بولندا|5XX XXX XXX|
PM|+508|Saint Pierre and Miquelon|سان بيير وميكلون|055 XX XX|0
PN|+64|Pitcairn Islands|جزر بيتكيرن|XXX|
PR|+1|Puerto Rico|بورتوريكو|787 234 5678|
PT|+351|Portugal|البرتغال|9XX XXX XXX|
PW|+680|Palau|بالاو|620 XXXX|
PY|+595|Paraguay|باراغواي|09XX XXX XXX|0
RE|+262|Réunion|ريونيون|0692 XX XX XX|0
RO|+40|Romania|رومانيا|07XX XXX XXX|0
RS|+381|Serbia|صربيا|06X XXX XXXX|0
RU|+7|Russia|روسيا|8 9XX XXX XX XX|8
RW|+250|Rwanda|رواندا|07XX XXX XXX|0
SB|+677|Solomon Islands|جزر سليمان|7XXXX|
SC|+248|Seychelles|سيشل|2 XXX XXX|
SE|+46|Sweden|السويد|07X XXX XX XX|0
SG|+65|Singapore|سنغافورة|8XXX XXXX|
SH|+290|Saint Helena|سانت هيلينا|5XXXX|
SI|+386|Slovenia|سلوفينيا|03X XXX XXX|0
SJ|+47|Svalbard and Jan Mayen|سفالبارد ويان ماين|4XX XX XXX|
SK|+421|Slovakia|سلوفاكيا|09XX XXX XXX|0
SL|+232|Sierra Leone|سيراليون|07X XXX XXX|0
SM|+378|San Marino|سان مارينو|66 XX XX XX|
SN|+221|Senegal|السنغال|7X XXX XX XX|
SR|+597|Suriname|سورينام|7XX XXXX|
SS|+211|South Sudan|جنوب السودان|09XX XXX XXX|0
ST|+239|São Tomé and Príncipe|ساو تومي وبرينسيبي|98X XXXX|
SV|+503|El Salvador|السلفادور|7XXX XXXX|
SX|+1|Sint Maarten|سينت مارتن|721 520 1234|
SZ|+268|Eswatini|إسواتيني|7XXX XXXX|
TC|+1|Turks and Caicos Islands|جزر توركس وكايكوس|649 231 1234|
TD|+235|Chad|تشاد|6X XX XX XX|
TF|+262|French Southern Territories|الأقاليم الجنوبية الفرنسية|0262 XX XX XX|0
TG|+228|Togo|توغو|9X XX XX XX|
TH|+66|Thailand|تايلاند|08X XXX XXXX|0
TJ|+992|Tajikistan|طاجيكستان|9X XXX XXXX|0
TK|+690|Tokelau|توكيلاو|7XXX|
TL|+670|Timor-Leste|تيمور الشرقية|7XX XXXX|
TM|+993|Turkmenistan|تركمانستان|06X XXXXXX|0
TO|+676|Tonga|تونغا|7XXXX|
TR|+90|Türkiye|تركيا|05XX XXX XX XX|0
TT|+1|Trinidad and Tobago|ترينيداد وتوباغو|868 291 1234|
TV|+688|Tuvalu|توفالو|90XXXX|
TW|+886|Taiwan|تايوان|09XX XXX XXX|0
TZ|+255|Tanzania|تنزانيا|07XX XXX XXX|0
UA|+380|Ukraine|أوكرانيا|0XX XXX XX XX|0
UG|+256|Uganda|أوغندا|07XX XXX XXX|0
US|+1|United States|الولايات المتحدة|202 555 0123|
UY|+598|Uruguay|أوروغواي|09X XXX XXX|0
UZ|+998|Uzbekistan|أوزبكستان|9X XXX XX XX|0
VA|+39|Vatican City|الفاتيكان|06 698 XXXXX|
VC|+1|Saint Vincent and the Grenadines|سانت فنسنت والغرينادين|784 430 1234|
VE|+58|Venezuela|فنزويلا|04XX XXX XXXX|0
VG|+1|British Virgin Islands|جزر العذراء البريطانية|284 300 1234|
VI|+1|U.S. Virgin Islands|جزر العذراء الأمريكية|340 642 1234|
VN|+84|Vietnam|فيتنام|09X XXX XXXX|0
VU|+678|Vanuatu|فانواتو|5XXXX|
WF|+681|Wallis and Futuna|واليس وفوتونا|82 XX XX|
WS|+685|Samoa|ساموا|7X XXX XX|
XK|+383|Kosovo|كوسوفو|04X XXX XXX|0
YT|+262|Mayotte|مايوت|0639 XX XX XX|0
ZA|+27|South Africa|جنوب أفريقيا|08X XXX XXXX|0
ZM|+260|Zambia|زامبيا|09X XXX XXXX|0
ZW|+263|Zimbabwe|زيمبابوي|07X XXX XXXX|0
""".strip().splitlines()


def _flag_for(country_code):
    return "".join(chr(127397 + ord(character)) for character in country_code)


_DOMESTIC_PREFIX_OVERRIDES = {
    "AG": "1",
    "AI": "1",
    "AR": "0",
    "AS": "1",
    "BB": "1",
    "BM": "1",
    "BO": "0",
    "BR": "0",
    "BS": "1",
    "CA": "1",
    "CG": "",
    "CI": "",
    "CN": "0",
    "CO": "0",
    "CU": "0",
    "DM": "1",
    "DO": "1",
    "GA": "",
    "GD": "1",
    "GE": "0",
    "GU": "1",
    "IN": "0",
    "JM": "1",
    "KI": "0",
    "KN": "1",
    "KY": "1",
    "LC": "1",
    "LI": "0",
    "MH": "1",
    "MN": "0",
    "MP": "1",
    "MS": "1",
    "MZ": "",
    "NP": "0",
    "PE": "0",
    "PR": "1",
    "SO": "0",
    "SX": "1",
    "TC": "1",
    "TJ": "",
    "TT": "1",
    "US": "1",
    "UZ": "",
    "VC": "1",
    "VG": "1",
    "VI": "1",
    "YE": "0",
}


def _domestic_prefix(country_code, stored_prefix):
    return _DOMESTIC_PREFIX_OVERRIDES.get(country_code, stored_prefix)


def _national_number_example(domestic_example, domestic_prefix):
    if not domestic_prefix:
        return domestic_example

    position = 0
    for prefix_character in domestic_prefix:
        while position < len(domestic_example) and domestic_example[position] in " -()./":
            position += 1
        if position >= len(domestic_example) or domestic_example[position] != prefix_character:
            return domestic_example
        position += 1
    return domestic_example[position:].lstrip(" -()./")


INTERNATIONAL_PHONE_COUNTRIES = tuple(
    {
        "code": code,
        "dial_code": dial_code,
        "flag": _flag_for(code),
        "name_en": name_en,
        "name_ar": name_ar,
        "example": _national_number_example(
            example,
            _domestic_prefix(code, national_prefix),
        ),
        "national_prefix": _domestic_prefix(code, national_prefix),
    }
    for code, dial_code, name_en, name_ar, example, national_prefix in (
        row.split("|") for row in _COUNTRY_ROWS
    )
)
