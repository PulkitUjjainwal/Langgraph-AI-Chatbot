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
