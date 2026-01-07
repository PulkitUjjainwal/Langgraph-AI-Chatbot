"""
Test the chapter data formatter with actual API response
"""
import sys
sys.path.append('C:\\MI Ticket\\MI Chat Bot\\Scrapper Function')

from chatbot.integrations.apis.unified_formatter import UnifiedFormatter

# Simulate the actual API response structure (from user's example)
test_data = {
    "country_name": "Argentina",
    "data_type": "import",
    "hs_code": "49",
    "hierarchy_level": "chapter",
    "platform": "marketinside",
    "chapter_details": {
        "date_range": ["2024-11-01", "2025-10-31"],
        "chapter": "49",
        "chapter_name": "Printed Books, Newspaper, Pictures And Other Products Of The Printing Industry; Manuscripts, Typescripts And Plans",
        "data_type": "custom_data",
        "country": "Argentina",
        "direction": "import",
        "total_value": 6008462108.967531,
        "total_shipments": 288569,
        "total_importer_exporter": {"value": 1788},
        "total_buyer_supplier": {"value": 1},
        "chapter_table": [
            {
                "chapter": "4907",
                "chapter_description": "Unused Postage, Revenue Or Similar Stamps",
                "current_month_value": 2222514950,
                "current_month_count": 87,
                "current_year_value": 5877094920.999903,
                "current_year_value_percentage": "97.81"
            },
            {
                "chapter": "4901",
                "chapter_description": "Printed Books, Brochures, Leaflets",
                "current_month_value": 12949546.358539216,
                "current_month_count": 23095,
                "current_year_value": 101448504.73459461,
                "current_year_value_percentage": "1.69"
            }
        ],
        "montly_trends_table": [
            {
                "month": "November 2024",
                "total_value": 45698331.15958586,
                "total_count": 26876,
                "total_percentage": "0.76"
            },
            {
                "month": "October 2025",
                "total_value": 2240496314.5297384,
                "total_count": 25177,
                "total_percentage": "37.29"
            }
        ],
        "partners_countries_table": [
            {
                "country": "CHINA",
                "total_value": 94406535.60560502,
                "total_count": 34033,
                "total_percentage": "1.57"
            },
            {
                "country": "SPAIN",
                "total_value": 54355539.48649006,
                "total_count": 136751,
                "total_percentage": "0.90"
            }
        ],
        "ports_table": [
            {
                "port": "EZEIZA",
                "total_value": 5828239726.615448,
                "total_count": 177535,
                "total_percentage": "97.00"
            }
        ],
        "importer_exporter_table": [
            {
                "company": "Banco Central De La Republica Argentina",
                "company_code": "3050001138",
                "total_value": 2607831155,
                "total_count": 25,
                "total_percentage": "43.40"
            }
        ],
        "buyer_supplier_table": [],
        "shipment_records": [
            {
                "date": "2025-10-24T00:00:00.000Z",
                "hs_code": ["49019900990"],
                "total_value_usd": 12.26,
                "unit": "Units",
                "quantity": 335,
                "origin_country": "SPAIN",
                "net_weight_kg": 0,
                "product_description": "Other Books, Booklets And Similar Prints"
            }
        ],
        "faq": [
            {
                "question": "What is Argentina import data?",
                "answer": "Argentina import data covers detailed information on shipments that enter into the country."
            }
        ]
    }
}

# Format the data
print("=" * 80)
print("TESTING CHAPTER FORMATTER")
print("=" * 80)
print()

formatted_text = UnifiedFormatter.format_hs_code_data(test_data)

print(formatted_text)
print()
print("=" * 80)
print(f"RESULT: Formatted text is {len(formatted_text)} characters")
print("=" * 80)
print()

# Check if all important sections are present
sections_to_check = [
    "[HS CODE CHAPTER - MARKETINSIDE]",
    "[CHAPTER DETAILS]",
    "[OVERALL STATISTICS]",
    "[HEADINGS UNDER THIS CHAPTER]",
    "[MONTHLY TRADE TRENDS]",
    "[TOP TRADING PARTNER COUNTRIES]",
    "[TOP PORTS]",
    "[TOP IMPORTERS]",
    "[RECENT SHIPMENT RECORDS]",
    "[FREQUENTLY ASKED QUESTIONS]"
]

print("SECTION CHECKLIST:")
for section in sections_to_check:
    present = "✓" if section in formatted_text else "✗"
    print(f"  {present} {section}")

print()
print(f"SUCCESS: Formatter now generates {len(formatted_text)} chars instead of 310 chars!")
