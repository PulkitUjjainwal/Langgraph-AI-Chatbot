"""
Unified Response Formatter

Converts API responses to formatted text for RAG/LLM consumption
Works with both Export Genius and Marketinside responses
"""

from typing import Dict, Any
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)


class UnifiedFormatter:
    """Format API responses as text for embeddings"""

    @staticmethod
    def format_company_data(data: Dict[str, Any]) -> str:
        """
        Format company data for RAG context

        Args:
            data: Company data from unified API client

        Returns:
            Formatted text
        """
        if "error" in data:
            return f"Error fetching company data: {data.get('error')}"

        sections = []
        platform = data.get("platform", "unknown")

        # ===================================================================
        # COMPANY OVERVIEW
        # ===================================================================
        overview = data.get("overview", {})
        if overview and "error" not in overview:
            sections.append(f"""[COMPANY OVERVIEW - {platform.upper()}]
Company Name: {overview.get('company_name', 'N/A')}
Address: {overview.get('address', 'N/A')}
Country: {overview.get('country_name', 'N/A')}
Headquarter: {overview.get('headquarter', 'N/A')}
Date Range: {overview.get('date_from', 'N/A')} to {overview.get('date_to', 'N/A')}
Import Turnover: ${overview.get('import_turnover', 0):,.2f}
Export Turnover: ${overview.get('export_turnover', 0):,.2f}
Import Shipments: {overview.get('import_shipments', 0):,}
Export Shipments: {overview.get('export_shipments', 0):,}
Website: {overview.get('websiteurl') or 'N/A'}
Phone: {overview.get('phone') or 'N/A'}
Industry: {overview.get('industry') or 'N/A'}""")

        # ===================================================================
        # TRADING COUNTRIES
        # ===================================================================
        countries = data.get("countries", {})
        if countries and "error" not in countries:
            imports = countries.get("imports", [])
            exports = countries.get("exports", [])

            if imports or exports:
                sections.append("\n[TOP TRADING COUNTRIES]")

                if imports:
                    sections.append("Import Countries:")
                    for item in imports[:10]:
                        country = item.get('country', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {country}: Value={value}, Share={percentage}%")

                if exports:
                    sections.append("\nExport Countries:")
                    for item in exports[:10]:
                        country = item.get('country', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {country}: Value={value}, Share={percentage}%")

        # ===================================================================
        # MONTHLY TURNOVER TRENDS
        # ===================================================================
        turnover = data.get("turnover", {})
        if turnover and "error" not in turnover:
            imports = turnover.get("imports", [])
            exports = turnover.get("exports", [])

            if imports or exports:
                sections.append("\n[MONTHLY TURNOVER TRENDS]")

                if imports:
                    sections.append("\nImport Trends (Last 12 Months):")
                    for month_data in imports[-12:]:
                        month = month_data.get('month', 'N/A')
                        value = month_data.get('value', 'locked')
                        sections.append(f"  • {month}: {value}")

                if exports:
                    sections.append("\nExport Trends (Last 12 Months):")
                    for month_data in exports[-12:]:
                        month = month_data.get('month', 'N/A')
                        value = month_data.get('value', 'locked')
                        sections.append(f"  • {month}: {value}")

        # ===================================================================
        # TOP COMMODITIES
        # ===================================================================
        commodities = data.get("commodities", {})
        if commodities and "error" not in commodities:
            imports = commodities.get("imports", [])
            exports = commodities.get("exports", [])

            if imports or exports:
                sections.append("\n[TOP COMMODITIES]")

                if imports:
                    sections.append("\nTop Import Products:")
                    for idx, item in enumerate(imports[:15], 1):
                        product = item.get('comodity_description', 'N/A')
                        hs_code = item.get('hs_code', 'N/A')
                        value = item.get('value', 'locked')
                        sections.append(f"  {idx}. HS {hs_code}: {product[:80]}")
                        sections.append(f"     Value={value}")

                if exports:
                    sections.append("\nTop Export Products:")
                    for idx, item in enumerate(exports[:15], 1):
                        product = item.get('comodity_description', 'N/A')
                        hs_code = item.get('hs_code', 'N/A')
                        value = item.get('value', 'locked')
                        sections.append(f"  {idx}. HS {hs_code}: {product[:80]}")
                        sections.append(f"     Value={value}")

        # ===================================================================
        # COMPETITORS
        # ===================================================================
        competitors = data.get("competitors", {})
        if competitors and "error" not in competitors:
            import_comps = competitors.get("import_competitors", [])
            export_comps = competitors.get("export_competitors", [])

            if import_comps or export_comps:
                sections.append("\n[COMPETITORS]")

                if import_comps:
                    sections.append("\nImport Competitors:")
                    for idx, comp in enumerate(import_comps[:10], 1):
                        name = comp.get('competitor', 'N/A')
                        turnover = comp.get('import_turnover', 'N/A')
                        sections.append(f"  {idx}. {name} - Turnover: ${turnover:,}")

                if export_comps:
                    sections.append("\nExport Competitors:")
                    for idx, comp in enumerate(export_comps[:10], 1):
                        name = comp.get('competitor', 'N/A')
                        turnover = comp.get('export_turnover', 'N/A')
                        sections.append(f"  {idx}. {name} - Turnover: ${turnover:,}")

        # ===================================================================
        # TOP PORTS
        # ===================================================================
        ports = data.get("ports", {})
        if ports and "error" not in ports:
            loading = ports.get("loading", [])
            unloading = ports.get("unloading", [])

            if loading or unloading:
                sections.append("\n[TOP PORTS]")

                if loading:
                    sections.append("\nLoading Ports (Export):")
                    for idx, port in enumerate(loading[:10], 1):
                        port_name = port.get('port_of_loading', 'N/A')
                        country = port.get('port_country', 'N/A')
                        value = port.get('value', 'locked')
                        sections.append(f"  {idx}. {port_name} ({country}): {value}")

                if unloading:
                    sections.append("\nUnloading Ports (Import):")
                    for idx, port in enumerate(unloading[:10], 1):
                        port_name = port.get('port_of_unloading', 'N/A')
                        country = port.get('port_country', 'N/A')
                        value = port.get('value', 'locked')
                        sections.append(f"  {idx}. {port_name} ({country}): {value}")

        # ===================================================================
        # RECENT SHIPMENTS
        # ===================================================================
        shipments = data.get("shipments", {})
        if shipments and "error" not in shipments:
            import_shipments = shipments.get("import_shipments", [])
            export_shipments = shipments.get("export_shipments", [])

            if import_shipments or export_shipments:
                sections.append("\n[RECENT SHIPMENTS]")

                if import_shipments:
                    sections.append("\nRecent Import Shipments:")
                    for idx, shipment in enumerate(import_shipments[:10], 1):
                        date = shipment.get('date', 'N/A')[:10]
                        product = shipment.get('product_description', 'N/A')
                        origin = shipment.get('origin_country', 'N/A')
                        hs_code = shipment.get('hs_code', 'N/A')
                        sections.append(f"  {idx}. {date} - HS {hs_code}")
                        sections.append(f"     {product[:100]}")
                        sections.append(f"     Origin: {origin}")

                if export_shipments:
                    sections.append("\nRecent Export Shipments:")
                    for idx, shipment in enumerate(export_shipments[:10], 1):
                        date = shipment.get('date', 'N/A')[:10]
                        product = shipment.get('product_description', 'N/A')
                        destination = shipment.get('destination_country', 'N/A')
                        hs_code = shipment.get('hs_code', 'N/A')
                        sections.append(f"  {idx}. {date} - HS {hs_code}")
                        sections.append(f"     {product[:100]}")
                        sections.append(f"     Destination: {destination}")

        # ===================================================================
        # FAQs
        # ===================================================================
        faqs = data.get("faqs", {})
        if faqs and "error" not in faqs:
            if any(v for k, v in faqs.items() if k != "error"):
                sections.append("\n[FREQUENTLY ASKED QUESTIONS]")

                for key, value in faqs.items():
                    if key != "error" and value:
                        # Convert key to readable format
                        readable_key = key.replace('_', ' ').title()
                        sections.append(f"\n{readable_key}:")
                        sections.append(f"  {value}")

        return "\n".join(sections)

    @staticmethod
    def format_country_data(data: Dict[str, Any]) -> str:
        """
        Format country data for RAG context

        Args:
            data: Country data from unified API client

        Returns:
            Formatted text
        """
        if "error" in data:
            return f"Error fetching country data: {data.get('error')}"

        sections = []
        country_code = data.get("country_code", "Unknown")
        data_type = data.get("data_type", "import")
        platform = data.get("platform", "unknown")

        # ===================================================================
        # COUNTRY STATISTICS
        # ===================================================================
        stats = data.get("stats", {})
        if stats and "error" not in stats:
            date_range = stats.get('date_range', [])
            date_from = date_range[0] if len(date_range) > 0 else 'N/A'
            date_to = date_range[1] if len(date_range) > 1 else 'N/A'

            total_value = stats.get('total_shipment_value', 0)
            shipment_count = stats.get('shipment_records', 0)
            importers_count = stats.get('importers', 0)
            suppliers_count = stats.get('suppliers', 0)

            sections.append(f"""[COUNTRY STATISTICS - {country_code.upper()} {data_type.upper()} - {platform.upper()}]
Country: {country_code.title()}
Data Type: {data_type.title()}
Total Shipment Value: ${total_value:,.2f}
Total Shipment Records: {shipment_count:,}
Number of Importers: {importers_count:,}
Number of Suppliers: {suppliers_count:,}
Date Range: {date_from} to {date_to}""")

        # ===================================================================
        # TOP IMPORTERS/EXPORTERS
        # ===================================================================
        importers = data.get("importers", {})
        if importers and "error" not in importers:
            top_companies = importers.get("portImportData", [])
            if top_companies:
                sections.append(f"\n[TOP {data_type.upper()}ERS]")
                for idx, company in enumerate(top_companies[:15], 1):
                    name = company.get('importer', company.get('exporter', 'N/A'))
                    value = company.get('import_value', company.get('export_value', 'N/A'))
                    shipments = company.get('shipment_count', 'N/A')
                    sections.append(f"  {idx}. {name}")
                    sections.append(f"     Value: {value}, Shipments: {shipments}")

        # ===================================================================
        # TOP TRADING PARTNERS
        # ===================================================================
        partners = data.get("partners", {})
        if partners and "error" not in partners:
            partner_list = partners.get("monthlyImportData", [])
            if partner_list:
                sections.append(f"\n[TOP TRADING PARTNERS]")
                for idx, partner in enumerate(partner_list[:15], 1):
                    country_name = partner.get('partner_country', partner.get('country', 'N/A'))
                    value = partner.get('trade_value', partner.get('value', 'N/A'))
                    sections.append(f"  {idx}. {country_name}: {value}")

        # ===================================================================
        # TOP PORTS
        # ===================================================================
        ports = data.get("ports", {})
        if ports and "error" not in ports:
            port_list = ports.get("portImportData", [])
            if port_list:
                sections.append(f"\n[TOP PORTS]")
                for idx, port in enumerate(port_list[:15], 1):
                    port_name = port.get('port_name', 'N/A')
                    value = port.get('port_value', 'N/A')
                    shipments = port.get('shipment_count', 'N/A')
                    sections.append(f"  {idx}. {port_name}: Value={value}, Shipments={shipments}")

        # ===================================================================
        # TOP HS CHAPTERS
        # ===================================================================
        chapters = data.get("chapters", {})
        if chapters and "error" not in chapters:
            chapter_list = chapters if isinstance(chapters, list) else chapters.get("data", [])
            if chapter_list:
                sections.append(f"\n[TOP HS CODE CHAPTERS]")
                for idx, chapter in enumerate(chapter_list[:15], 1):
                    # API returns: chapter_code, chapter_description, current_year_usd
                    hs_code = chapter.get('chapter_code', chapter.get('hs_code', 'N/A'))
                    description = chapter.get('chapter_description', chapter.get('description', 'N/A'))
                    value = chapter.get('current_year_usd', chapter.get('value', 'N/A'))
                    share = chapter.get('total_share_value_last_12_months', '')

                    # Format value
                    if isinstance(value, (int, float)):
                        value_str = f"${value:,.2f}"
                    elif isinstance(value, str) and value != 'N/A':
                        try:
                            value_str = f"${float(value):,.2f}"
                        except:
                            value_str = value
                    else:
                        value_str = value

                    # Add share percentage if available
                    share_str = f" ({share}% of total)" if share else ""

                    sections.append(f"  {idx}. Chapter {hs_code} - {description[:60]}: {value_str}{share_str}")

        # ===================================================================
        # TOP COMMODITIES
        # ===================================================================
        commodities = data.get("commodities", {})
        if commodities and "error" not in commodities:
            commodity_list = commodities if isinstance(commodities, list) else commodities.get("data", [])
            if commodity_list:
                sections.append(f"\n[TOP COMMODITIES]")
                for idx, commodity in enumerate(commodity_list[:15], 1):
                    name = commodity.get('commodity', 'N/A')
                    value = commodity.get('value', 'N/A')
                    sections.append(f"  {idx}. {name}: {value}")

        # ===================================================================
        # MONTHLY TRENDS
        # ===================================================================
        monthly = data.get("monthly", {})
        if monthly and "error" not in monthly:
            trends = monthly.get("monthlyImportData", [])
            if trends:
                sections.append(f"\n[MONTHLY TRENDS (Last 12 Months)]")
                for trend in trends[-12:]:
                    month = trend.get('month', trend.get('period', 'N/A'))
                    value = trend.get('monthly_value', trend.get('value', 'N/A'))
                    sections.append(f"  • {month}: {value}")

        # ===================================================================
        # BUYER/SUPPLIER DATA
        # ===================================================================
        buyer_supplier = data.get("buyer_supplier", {})
        if buyer_supplier and "error" not in buyer_supplier:
            # Format buyer/supplier data if available
            buyers = buyer_supplier.get("buyers", [])
            suppliers = buyer_supplier.get("suppliers", [])

            if buyers or suppliers:
                sections.append(f"\n[BUYERS & SUPPLIERS]")

                if buyers:
                    sections.append("\nTop Buyers:")
                    for idx, buyer in enumerate(buyers[:10], 1):
                        name = buyer.get('buyer_name', buyer.get('name', 'N/A'))
                        sections.append(f"  {idx}. {name}")

                if suppliers:
                    sections.append("\nTop Suppliers:")
                    for idx, supplier in enumerate(suppliers[:10], 1):
                        name = supplier.get('supplier_name', supplier.get('name', 'N/A'))
                        sections.append(f"  {idx}. {name}")

        return "\n".join(sections) if sections else f"No data available for {country_code}"

    @staticmethod
    def format_search_data(data: Dict[str, Any]) -> str:
        """
        Format search data for RAG context

        Args:
            data: Search data from unified API client

        Returns:
            Formatted text
        """
        if "error" in data:
            return f"Error fetching search data: {data.get('error')}"

        sections = []
        params = data.get("search_params", {})
        platform = data.get("platform", "unknown")

        # ===================================================================
        # SEARCH PARAMETERS
        # ===================================================================
        sections.append(f"[SEARCH DATA - {platform.upper()}]")
        sections.append(f"\nSearch Query:")
        sections.append(f"  Type: {params.get('type', 'N/A')}")
        sections.append(f"  Country: {params.get('country', 'Universal')}")
        if params.get('product'):
            sections.append(f"  Product: {params['product']}")
        if params.get('hs_code'):
            sections.append(f"  HS Code: {params['hs_code']}")
        sections.append("")

        # ===================================================================
        # MAIN TRADE DATA
        # ===================================================================
        product_data = data.get("search_data_product", {})
        if product_data and "error" not in product_data:
            sections.append("\n=== TRADE DATA ===")

            # Get total value (may come from product_data or importers_data)
            total_value = product_data.get('total_value_usd', 0)
            if isinstance(total_value, str):
                total_value = float(total_value) if total_value else 0

            total_shipments = product_data.get('total_shipments', 0)

            # If product endpoint has data, show it
            if total_shipments or total_value:
                sections.append(f"Total Shipments: {total_shipments:,}")
                sections.append(f"Total Value: ${total_value:,.2f}")

            date_range = product_data.get('date_range', [])
            if date_range:
                sections.append(f"Date Range: {date_range[0]} to {date_range[1]}")

            # Top shipment records (limit to 20)
            products = product_data.get('products', [])[:20]
            if products:
                sections.append(f"\nTop {len(products)} Shipment Records:")
                for i, product in enumerate(products, 1):
                    sections.append(f"\n{i}. {product.get('product_description', 'N/A')[:150]}")
                    sections.append(f"   Importer: {product.get('importer', 'N/A')}")
                    sections.append(f"   Exporter: {product.get('exporter', 'N/A')}")

                    value = product.get('total_value_usd', product.get('value_usd', 0))
                    if isinstance(value, str):
                        if value.lower() == 'locked':
                            sections.append(f"   Value: [Locked]")
                        else:
                            try:
                                value = float(value)
                                sections.append(f"   Value: ${value:,.2f}")
                            except ValueError:
                                sections.append(f"   Value: {value}")
                    else:
                        sections.append(f"   Value: ${value:,.2f}")

                    sections.append(f"   HS Code: {product.get('hs_code', 'N/A')}")
                    sections.append(f"   Origin: {product.get('origin_country', 'N/A')}")

        # ===================================================================
        # IMPORTERS
        # ===================================================================
        importers_data = data.get("search_data_importers", {})
        if importers_data and "error" not in importers_data:
            # Show total value from importers endpoint if not shown above
            if not product_data or (not product_data.get('total_shipments') and not product_data.get('total_value_usd')):
                total_value = importers_data.get('total_value_usd', 0)
                if isinstance(total_value, str):
                    total_value = float(total_value) if total_value else 0

                if total_value and "\n=== TRADE DATA ===" not in "\n".join(sections):
                    sections.append("\n=== TRADE DATA ===")
                    sections.append(f"Total Trade Value: ${total_value:,.2f}")

                    date_range = importers_data.get('date_range', [])
                    if date_range:
                        sections.append(f"Date Range: {date_range[0]} to {date_range[1]}")

            # Show top importers
            importers = importers_data.get('importers', [])[:15]
            if importers:
                sections.append("\n=== TOP IMPORTERS ===")
                for i, importer in enumerate(importers, 1):
                    # Handle both field name variations
                    importer_name = importer.get('importer', importer.get('importer_name', 'N/A'))
                    country = importer.get('origin_country', importer.get('country', 'N/A'))
                    count = importer.get('count', importer.get('total_shipments', 0))
                    value = importer.get('value_usd', importer.get('total_value_usd', 0))

                    # Convert value if it's a string
                    value_str = ""
                    if isinstance(value, str):
                        if value.lower() == 'locked':
                            value_str = "[Locked]"
                        else:
                            try:
                                value_str = f"${float(value):,.2f}"
                            except ValueError:
                                value_str = value
                    else:
                        value_str = f"${value:,.2f}"

                    sections.append(f"{i}. {importer_name}")
                    if country != 'N/A':
                        sections.append(f"   Origin: {country}")
                    sections.append(f"   Shipments: {count:,}")
                    sections.append(f"   Value: {value_str}")

                    # Show product description if available
                    product_desc = importer.get('product_desc', '')
                    if product_desc:
                        sections.append(f"   Product: {product_desc[:100]}")

        # ===================================================================
        # EXPORTERS
        # ===================================================================
        exporters_data = data.get("search_data_exporters", {})
        if exporters_data and "error" not in exporters_data:
            exporters = exporters_data.get('exporters', [])[:15]
            if exporters:
                sections.append("\n=== TOP EXPORTERS ===")
                for i, exporter in enumerate(exporters, 1):
                    sections.append(f"{i}. {exporter.get('exporter_name', 'N/A')}")
                    sections.append(f"   Country: {exporter.get('country', 'N/A')}")
                    sections.append(f"   Shipments: {exporter.get('total_shipments', 0):,}")
                    sections.append(f"   Value: ${exporter.get('total_value_usd', 0):,.2f}")

        # ===================================================================
        # BUYERS
        # ===================================================================
        buyers_data = data.get("search_data_buyers", {})
        if buyers_data and "error" not in buyers_data:
            buyers = buyers_data.get('buyers', [])[:15]
            if buyers:
                sections.append("\n=== TOP BUYERS ===")
                for i, buyer in enumerate(buyers, 1):
                    sections.append(f"{i}. {buyer.get('buyer_name', 'N/A')}")
                    sections.append(f"   Country: {buyer.get('country', 'N/A')}")
                    sections.append(f"   Shipments: {buyer.get('total_shipments', 0):,}")

        # ===================================================================
        # SUPPLIERS
        # ===================================================================
        suppliers_data = data.get("search_data_suppliers", {})
        if suppliers_data and "error" not in suppliers_data:
            suppliers = suppliers_data.get('suppliers', [])[:15]
            if suppliers:
                sections.append("\n=== TOP SUPPLIERS ===")
                for i, supplier in enumerate(suppliers, 1):
                    sections.append(f"{i}. {supplier.get('supplier_name', 'N/A')}")
                    sections.append(f"   Country: {supplier.get('country', 'N/A')}")
                    sections.append(f"   Shipments: {supplier.get('total_shipments', 0):,}")

        # ===================================================================
        # TOTALS
        # ===================================================================
        totals_imp = data.get("search_data_total_importers_suppliers", {})
        totals_exp = data.get("search_data_total_exporters_buyers", {})

        if (totals_imp and "error" not in totals_imp) or (totals_exp and "error" not in totals_exp):
            sections.append("\n=== TOTALS ===")

            if totals_imp and "error" not in totals_imp:
                sections.append(f"Total Importers: {totals_imp.get('totalImporters', 0):,}")
                sections.append(f"Total Foreign Suppliers: {totals_imp.get('totalForeignSuppliers', 0):,}")

            if totals_exp and "error" not in totals_exp:
                sections.append(f"Total Exporters: {totals_exp.get('totalExporters', 0):,}")
                sections.append(f"Total Foreign Buyers: {totals_exp.get('total_foreign_buyers', 0):,}")

        return "\n".join(sections)

    @staticmethod
    def format_country_to_country_data(data: Dict[str, Any]) -> str:
        """
        Format country-to-country bilateral trade data for RAG context

        Args:
            data: Country-to-country data from unified API client

        Returns:
            Formatted text
        """
        if "error" in data:
            return f"Error fetching country-to-country data: {data.get('error')}"

        sections = []
        origin_country = data.get("origin_country", "Unknown")
        destination_country = data.get("destination_country", "Unknown")
        data_type = data.get("data_type", "import")
        platform = data.get("platform", "unknown")

        # Convert country names to title case for better display
        origin_country_display = origin_country.title() if origin_country != "Unknown" else origin_country
        destination_country_display = destination_country.title() if destination_country != "Unknown" else destination_country

        # ===================================================================
        # BILATERAL TRADE STATISTICS
        # ===================================================================
        stats = data.get("stats", {})
        if stats and "error" not in stats:
            date_range = stats.get('date_range', [])
            date_from = date_range[0] if len(date_range) > 0 else 'N/A'
            date_to = date_range[1] if len(date_range) > 1 else 'N/A'

            # Get appropriate fields based on data_type
            if data_type == "import":
                total_value = stats.get('total_import_value', stats.get('import_value', 0))
                num_importers = stats.get('number_of_importers', 0)
                num_suppliers = stats.get('number_of_supplier', 0)
            else:  # export
                total_value = stats.get('total_export_value', stats.get('export_value', 0))
                num_importers = stats.get('number_of_buyer', 0)
                num_suppliers = stats.get('number_of_exporters', 0)

            # Convert total_value to float if it's a string
            if isinstance(total_value, str):
                try:
                    total_value = float(total_value)
                except ValueError:
                    total_value = 0

            market_share = stats.get('trade_partner_market_share', 'N/A')
            total_shipments = stats.get('total_shipments_arrived', 0)

            sections.append(f"""[BILATERAL TRADE DATA - {platform.upper()}]
Trade Route: {origin_country_display} {data_type.upper()}S FROM/TO {destination_country_display}
Total Trade Value: ${total_value:,.2f}
Market Share: {market_share}%
Total Shipments: {total_shipments:,}
Number of {"Importers" if data_type == "import" else "Buyers"}: {num_importers:,}
Number of {"Suppliers" if data_type == "import" else "Exporters"}: {num_suppliers:,}
Date Range: {date_from} to {date_to}""")

        # ===================================================================
        # TOP HS CODE CHAPTERS
        # ===================================================================
        chapters = data.get("chapters", {})
        if chapters and "error" not in chapters:
            chapter_list = chapters.get("chapters", [])
            if chapter_list:
                sections.append(f"\n[TOP HS CODE CHAPTERS]")
                for idx, chapter in enumerate(chapter_list[:15], 1):
                    chapter_code = chapter.get('chapter_code', 'N/A')
                    chapter_name = chapter.get('chapter', 'N/A')
                    description = chapter.get('chapter_description', 'N/A')

                    # Get value based on data_type
                    current_year_usd = chapter.get('current_year_usd', 0)
                    prev_year_usd = chapter.get('prev_year_usd', 0)

                    # Convert to float if string
                    if isinstance(current_year_usd, str):
                        try:
                            current_year_usd = float(current_year_usd)
                        except ValueError:
                            current_year_usd = 0

                    if isinstance(prev_year_usd, str):
                        try:
                            prev_year_usd = float(prev_year_usd)
                        except ValueError:
                            prev_year_usd = 0

                    share = chapter.get('total_share_value_last_12_months', '')
                    share_str = f" ({share}% of total)" if share else ""

                    sections.append(f"  {idx}. {chapter_name} (Code: {chapter_code})")
                    sections.append(f"     {description[:80]}")
                    sections.append(f"     Current Year: ${current_year_usd:,.2f}, Previous Year: ${prev_year_usd:,.2f}{share_str}")

        # ===================================================================
        # TOP COMPANIES (Importers/Exporters and Suppliers/Buyers)
        # ===================================================================
        companies = data.get("companies", {})
        if companies and "error" not in companies:
            if data_type == "import":
                primary_companies = companies.get("importers", [])
                secondary_companies = companies.get("suppliers", [])
                primary_label = "IMPORTERS"
                secondary_label = "SUPPLIERS"
            else:  # export
                primary_companies = companies.get("exporters", [])
                secondary_companies = companies.get("buyers", [])
                primary_label = "EXPORTERS"
                secondary_label = "BUYERS"

            if primary_companies:
                sections.append(f"\n[TOP {primary_label} IN {origin_country_display.upper()}]")
                for idx, company in enumerate(primary_companies[:15], 1):
                    company_name = company.get('importer', company.get('exporter', 'N/A'))
                    value = company.get('value_usd', 0)

                    # Convert to float if string
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = 0

                    percentage = company.get('percentage', '')
                    percentage_str = f" ({percentage}%)" if percentage else ""

                    sections.append(f"  {idx}. {company_name}")
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")

            if secondary_companies:
                sections.append(f"\n[TOP {secondary_label} IN {destination_country_display.upper()}]")
                for idx, company in enumerate(secondary_companies[:15], 1):
                    company_name = company.get('supplier', company.get('buyer', 'N/A'))
                    value = company.get('value_usd', 0)

                    # Convert to float if string
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = 0

                    percentage = company.get('percentage', '')
                    percentage_str = f" ({percentage}%)" if percentage else ""

                    sections.append(f"  {idx}. {company_name}")
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")

        # ===================================================================
        # RECENT SHIPMENTS
        # ===================================================================
        shipments = data.get("shipments", {})
        if shipments and "error" not in shipments:
            shipment_list = shipments.get("import_shipments", shipments.get("export_shipments", []))
            if shipment_list:
                sections.append(f"\n[RECENT SHIPMENT RECORDS]")
                for idx, shipment in enumerate(shipment_list[:10], 1):
                    date = shipment.get('date', 'N/A')
                    if isinstance(date, str) and 'T' in date:
                        date = date.split('T')[0]  # Extract just the date part

                    hs_code = shipment.get('hs_code', 'N/A')
                    product = shipment.get('product_description', 'N/A')
                    importer = shipment.get('importer', 'N/A')
                    supplier = shipment.get('supplier', shipment.get('exporter', 'N/A'))
                    value = shipment.get('total_value_usd', 0)
                    quantity = shipment.get('quantity', 'N/A')
                    unit = shipment.get('unit', '')

                    # Convert value to float if string
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = 0

                    sections.append(f"  {idx}. Date: {date}")
                    sections.append(f"     HS Code: {hs_code}")
                    sections.append(f"     Product: {product[:100]}")
                    sections.append(f"     Importer: {importer}")
                    sections.append(f"     Supplier: {supplier}")
                    sections.append(f"     Value: ${value:,.2f}")
                    if quantity != 'N/A':
                        sections.append(f"     Quantity: {quantity} {unit}")

        # ===================================================================
        # TOP PORTS
        # ===================================================================
        ports = data.get("ports", {})
        if ports and "error" not in ports:
            port_list = ports.get("ports", [])
            if port_list:
                sections.append(f"\n[TOP PORTS HANDLING TRADE]")
                for idx, port in enumerate(port_list[:15], 1):
                    port_name = port.get('port', 'N/A')
                    value = port.get('value_usd', 0)

                    # Convert to float if string
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = 0

                    percentage = port.get('percentage', '')
                    percentage_str = f" ({percentage}%)" if percentage else ""

                    sections.append(f"  {idx}. {port_name}: ${value:,.2f}{percentage_str}")

        # ===================================================================
        # MONTHLY TRENDS
        # ===================================================================
        monthly_trends = data.get("monthly_trends", {})
        if monthly_trends and "error" not in monthly_trends:
            trends = monthly_trends.get("monthly_trends", [])
            if trends:
                sections.append(f"\n[MONTHLY TRADE TRENDS]")
                for trend in trends[-12:]:  # Last 12 months
                    month = trend.get('month', 'N/A')
                    value = trend.get('value', 0)

                    # Convert to float if string
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = 0

                    sections.append(f"  • {month}: ${value:,.2f}")

        return "\n".join(sections) if sections else f"No data available for trade between {origin_country_display} and {destination_country_display}"

    @staticmethod
    def format_hs_code_data(data: Dict[str, Any]) -> str:
        """
        Format HS code hierarchy data for RAG context
        Handles actual Marketinside API response structure

        Args:
            data: HS code data from unified API client

        Returns:
            Formatted text
        """
        if "error" in data:
            return f"Error fetching HS code data: {data.get('error')}"

        sections = []
        country_name = data.get("country_name", "Unknown")
        data_type = data.get("data_type", "import")
        hs_code = data.get("hs_code", "Unknown")
        hierarchy_level = data.get("hierarchy_level", "unknown")
        platform = data.get("platform", "unknown")

        # Convert country name to title case for display
        country_name_display = country_name.title() if country_name != "Unknown" else country_name

        # Get the actual API response data
        chapter_details = data.get("chapter_details", {})
        heading_details = data.get("heading_details", {})
        subheading_details = data.get("subheading_details", {})
        hs_code_details = data.get("hs_code_details", {})

        # Determine which details object to use based on hierarchy
        if hierarchy_level == "chapter":
            details = chapter_details
        elif hierarchy_level == "heading":
            details = heading_details
        elif hierarchy_level == "subheading":
            details = subheading_details
        else:
            details = hs_code_details

        if not details or "error" in details:
            return f"No data available for HS code {hs_code} in {country_name_display}"

        # ===================================================================
        # HEADER
        # ===================================================================
        sections.append(f"[HS CODE {hierarchy_level.upper()} - {platform.upper()}]")
        sections.append(f"Country: {country_name_display}")
        sections.append(f"Direction: {data_type.capitalize()}")
        sections.append(f"HS Code: {hs_code}")
        sections.append(f"Level: {hierarchy_level.replace('_', ' ').title()}")
        sections.append("")

        # ===================================================================
        # CHAPTER/HEADING/SUBHEADING DETAILS
        # ===================================================================
        sections.append(f"[{hierarchy_level.upper()} DETAILS]")

        # Chapter/Heading/Subheading code and name
        code_key = {
            "chapter": "chapter",
            "heading": "heading",
            "subheading": "sub_heading",
            "hs_code": "hs_code"
        }.get(hierarchy_level, "chapter")

        name_key = f"{hierarchy_level}_name" if hierarchy_level != "hs_code" else "chapter_name"

        code_value = details.get(code_key, details.get("chapter", hs_code))
        name_value = details.get(name_key, details.get("chapter_name", "N/A"))

        sections.append(f"{hierarchy_level.replace('_', ' ').title()} Code: {code_value}")
        sections.append(f"{hierarchy_level.replace('_', ' ').title()} Name: {name_value}")

        # Description if available
        description = details.get("description", "N/A")
        if description != "N/A":
            sections.append(f"Description: {description}")
        sections.append("")

        # ===================================================================
        # OVERALL STATISTICS
        # ===================================================================
        total_value = details.get("total_value", 0)
        total_shipments = details.get("total_shipments", 0)
        total_importer_exporter = details.get("total_importer_exporter", {})
        total_buyer_supplier = details.get("total_buyer_supplier", {})

        if total_value or total_shipments:
            sections.append("[OVERALL STATISTICS]")
            if isinstance(total_value, (int, float)):
                sections.append(f"Total Trade Value: ${total_value:,.2f}")
            if isinstance(total_shipments, (int, float)):
                sections.append(f"Total Shipments: {total_shipments:,}")
            if total_importer_exporter and isinstance(total_importer_exporter.get("value"), (int, float)):
                sections.append(f"Total Importers/Exporters: {total_importer_exporter.get('value'):,}")
            if total_buyer_supplier and isinstance(total_buyer_supplier.get("value"), (int, float)):
                sections.append(f"Total Buyers/Suppliers: {total_buyer_supplier.get('value'):,}")
            sections.append("")

        # ===================================================================
        # SUB-ITEMS (Chapter Table / Heading List / Subheading List)
        # ===================================================================
        # For chapter: chapter_table contains headings
        # For heading: similar structure with subheadings
        # For subheading: hs code list

        chapter_table = details.get("chapter_table", [])
        if chapter_table and isinstance(chapter_table, list):
            if hierarchy_level == "chapter":
                label = "HEADINGS UNDER THIS CHAPTER"
            elif hierarchy_level == "heading":
                label = "SUBHEADINGS UNDER THIS HEADING"
            else:
                label = "HS CODES UNDER THIS SUBHEADING"

            sections.append(f"[{label}]")
            sections.append(f"Total Items: {len(chapter_table)}")
            sections.append("")

            for idx, item in enumerate(chapter_table[:15], 1):  # Limit to top 15
                item_code = item.get("chapter", item.get("heading", item.get("hs_code", "N/A")))
                item_desc = item.get("chapter_description", item.get("heading_description", item.get("description", "N/A")))
                current_year_value = item.get("current_year_value", 0)
                current_year_count = item.get("current_year_count", 0)
                percentage = item.get("current_year_value_percentage", "")

                sections.append(f"  {idx}. {item_code}: {item_desc[:80]}")
                if isinstance(current_year_value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"     Value: ${current_year_value:,.2f}{percentage_str}")
                if isinstance(current_year_count, (int, float)) and current_year_count > 0:
                    sections.append(f"     Shipments: {current_year_count:,}")
                sections.append("")

            if len(chapter_table) > 15:
                sections.append(f"  ... and {len(chapter_table) - 15} more items")
            sections.append("")

        # ===================================================================
        # MONTHLY TRENDS
        # ===================================================================
        monthly_trends = details.get("montly_trends_table", [])  # Note: API has typo "montly"
        if monthly_trends and isinstance(monthly_trends, list):
            sections.append("[MONTHLY TRADE TRENDS]")
            sections.append(f"Showing last {min(12, len(monthly_trends))} months:")
            sections.append("")

            for trend in monthly_trends[-12:]:  # Last 12 months
                month = trend.get("month", "N/A")
                value = trend.get("total_value", 0)
                count = trend.get("total_count", 0)
                percentage = trend.get("total_percentage", "")

                if isinstance(value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"  • {month}: ${value:,.2f}{percentage_str} - {count:,} shipments")
            sections.append("")

        # ===================================================================
        # TOP PARTNER COUNTRIES
        # ===================================================================
        partners = details.get("partners_countries_table", [])
        if partners and isinstance(partners, list):
            sections.append("[TOP TRADING PARTNER COUNTRIES]")
            for idx, partner in enumerate(partners[:15], 1):
                country = partner.get("country", "N/A")
                value = partner.get("total_value", 0)
                count = partner.get("total_count", 0)
                percentage = partner.get("total_percentage", "")

                sections.append(f"  {idx}. {country}")
                if isinstance(value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")
                if isinstance(count, (int, float)):
                    sections.append(f"     Shipments: {count:,}")
            sections.append("")

        # ===================================================================
        # TOP PORTS
        # ===================================================================
        ports = details.get("ports_table", [])
        if ports and isinstance(ports, list):
            sections.append("[TOP PORTS]")
            for idx, port in enumerate(ports[:15], 1):
                port_name = port.get("port", "N/A")
                value = port.get("total_value", 0)
                count = port.get("total_count", 0)
                percentage = port.get("total_percentage", "")

                sections.append(f"  {idx}. {port_name}")
                if isinstance(value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")
                if isinstance(count, (int, float)):
                    sections.append(f"     Shipments: {count:,}")
            sections.append("")

        # ===================================================================
        # TOP IMPORTERS/EXPORTERS
        # ===================================================================
        companies = details.get("importer_exporter_table", [])
        if companies and isinstance(companies, list):
            company_type = "IMPORTERS" if data_type == "import" else "EXPORTERS"
            sections.append(f"[TOP {company_type}]")

            for idx, company in enumerate(companies[:15], 1):
                company_name = company.get("company", "N/A")
                company_code = company.get("company_code", "")
                value = company.get("total_value", 0)
                count = company.get("total_count", 0)
                percentage = company.get("total_percentage", "")

                sections.append(f"  {idx}. {company_name}")
                if company_code:
                    sections.append(f"     Code: {company_code}")
                if isinstance(value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")
                if isinstance(count, (int, float)):
                    sections.append(f"     Shipments: {count:,}")
            sections.append("")

        # ===================================================================
        # TOP BUYERS/SUPPLIERS
        # ===================================================================
        buyer_supplier = details.get("buyer_supplier_table", [])
        if buyer_supplier and isinstance(buyer_supplier, list):
            bs_type = "SUPPLIERS" if data_type == "import" else "BUYERS"
            sections.append(f"[TOP {bs_type}]")

            for idx, bs in enumerate(buyer_supplier[:15], 1):
                bs_name = bs.get("company", "N/A")
                value = bs.get("total_value", 0)
                count = bs.get("total_count", 0)
                percentage = bs.get("total_percentage", "")

                sections.append(f"  {idx}. {bs_name}")
                if isinstance(value, (int, float)):
                    percentage_str = f" ({percentage}%)" if percentage else ""
                    sections.append(f"     Value: ${value:,.2f}{percentage_str}")
                if isinstance(count, (int, float)):
                    sections.append(f"     Shipments: {count:,}")
            sections.append("")

        # ===================================================================
        # SAMPLE SHIPMENT RECORDS
        # ===================================================================
        shipments = details.get("shipment_records", [])
        if shipments and isinstance(shipments, list):
            sections.append("[RECENT SHIPMENT RECORDS]")
            sections.append(f"Showing {min(10, len(shipments))} sample shipments:")
            sections.append("")

            for idx, shipment in enumerate(shipments[:10], 1):
                date = shipment.get("date", "N/A")
                if isinstance(date, str) and 'T' in date:
                    date = date.split('T')[0]

                hs_codes = shipment.get("hs_code", [])
                if isinstance(hs_codes, list) and hs_codes:
                    hs_code_str = hs_codes[0]
                else:
                    hs_code_str = str(hs_codes) if hs_codes else "N/A"

                product_desc = shipment.get("product_description", "N/A")
                value = shipment.get("total_value_usd", 0)
                quantity = shipment.get("quantity", 0)
                unit = shipment.get("unit", "")
                origin = shipment.get("origin_country", "N/A")
                weight = shipment.get("net_weight_kg", 0)

                sections.append(f"  {idx}. Date: {date}")
                sections.append(f"     HS Code: {hs_code_str}")
                sections.append(f"     Product: {product_desc[:100]}")
                sections.append(f"     Origin: {origin}")
                if isinstance(value, (int, float)) and value > 0:
                    sections.append(f"     Value: ${value:,.2f}")
                if quantity and unit:
                    sections.append(f"     Quantity: {quantity:,} {unit}")
                if isinstance(weight, (int, float)) and weight > 0:
                    sections.append(f"     Net Weight: {weight:,.2f} kg")
                sections.append("")

        # ===================================================================
        # FAQs
        # ===================================================================
        faqs = details.get("faq", [])
        if faqs and isinstance(faqs, list):
            sections.append("[FREQUENTLY ASKED QUESTIONS]")
            for faq in faqs[:10]:  # Limit to 10 FAQs
                question = faq.get("question", "")
                answer = faq.get("answer", "")
                if question and answer:
                    sections.append(f"\nQ: {question}")
                    sections.append(f"A: {answer}")
            sections.append("")

        return "\n".join(sections) if sections else f"No data available for HS code {hs_code} in {country_name_display}"
