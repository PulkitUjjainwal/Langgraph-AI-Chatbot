-- FAQ Database Schema for MI Chatbot
-- Database: chatbot

USE chatbot;

-- ============================================================================
-- PAGES TABLE - Stores page configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS pages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    page_key VARCHAR(100) NOT NULL UNIQUE COMMENT 'Unique identifier like: home, logistics, platform, api, data_license, search_data',
    page_name VARCHAR(255) NOT NULL COMMENT 'Display name for the page',
    url_pattern VARCHAR(500) NOT NULL COMMENT 'URL pattern to match (supports wildcards)',
    description TEXT COMMENT 'Page description',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_page_key (page_key),
    INDEX idx_url_pattern (url_pattern(255)),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- FAQ TABLE - Stores questions and answers
-- ============================================================================
CREATE TABLE IF NOT EXISTS faq (
    id INT AUTO_INCREMENT PRIMARY KEY,
    page_id INT NOT NULL COMMENT 'Foreign key to pages table',
    question TEXT NOT NULL COMMENT 'The question text',
    answer TEXT NOT NULL COMMENT 'Pre-defined answer (can include markdown)',
    question_type ENUM('suggested', 'faq') DEFAULT 'suggested' COMMENT 'suggested = shown in suggestions, faq = matched during chat',
    priority INT DEFAULT 0 COMMENT 'Display order (higher = shown first)',
    keywords VARCHAR(500) COMMENT 'Comma-separated keywords for fuzzy matching',
    is_active BOOLEAN DEFAULT TRUE,
    click_count INT DEFAULT 0 COMMENT 'Track how often this question is clicked',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE,
    INDEX idx_page_id (page_id),
    INDEX idx_question_type (question_type),
    INDEX idx_priority (priority DESC),
    INDEX idx_is_active (is_active),
    FULLTEXT INDEX idx_question_fulltext (question),
    FULLTEXT INDEX idx_keywords_fulltext (keywords)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- INSERT PAGE CONFIGURATIONS
-- ============================================================================
INSERT INTO pages (page_key, page_name, url_pattern, description) VALUES
('home', 'Homepage', 'https://www.marketinsidedata.com/%', 'Main landing page'),
('home_en', 'Homepage EN', 'https://www.marketinsidedata.com/en%', 'English homepage'),
('search_data', 'Search Data', '%/search-data%', 'Data search page'),
('data_license', 'Data License', '%/data-license%', 'Data licensing page'),
('logistics', 'Logistics Solutions', '%/logistics%', 'Logistics industry solutions'),
('platform', 'Platform', '%/platform%', 'Platform features page'),
('api', 'API Solutions', '%/api%', 'API documentation and solutions')
ON DUPLICATE KEY UPDATE page_name=VALUES(page_name), url_pattern=VALUES(url_pattern);

-- ============================================================================
-- INSERT HOMEPAGE FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
-- Homepage Suggested Questions (shown first)
((SELECT id FROM pages WHERE page_key = 'home'),
 'I want to find active global buyers',
 'Market Inside Data helps you discover active importers worldwide. Our platform tracks real shipment data across 100+ countries, showing you verified buyers with their import history, volumes, and contact details. You can filter by product, country, or time period to find the most relevant prospects for your business.',
 'suggested', 100, 'buyers,importers,global,find,active'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I need to track competitor activities',
 'With Market Inside Data, you can monitor your competitors'' export activities in real-time. See which markets they''re entering, their shipment volumes, pricing trends, and new business relationships. Our competitor tracking tools help you stay ahead of market changes.',
 'suggested', 99, 'competitor,track,monitor,activities,export'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I need verified decision maker emails',
 'Our database includes verified contact information for key decision makers at importing and exporting companies. Each contact is validated and includes email, phone, and company details. You can search by industry, country, or company name.',
 'suggested', 98, 'emails,contacts,decision,maker,verified'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I want to identify reliable suppliers',
 'Find trusted suppliers with our comprehensive export data. View supplier shipment history, reliability scores, product range, and customer reviews. Filter by country, product category, or certification to find the perfect manufacturing partner.',
 'suggested', 97, 'suppliers,reliable,identify,manufacturers,exporters'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I want to analyze market trends',
 'Our market analysis tools provide insights into trade patterns, demand fluctuations, and emerging opportunities. View historical trends, seasonal patterns, and growth forecasts by product or region to make data-driven decisions.',
 'suggested', 96, 'market,trends,analyze,analysis,forecast'),

-- Additional Homepage FAQs (for matching during chat)
((SELECT id FROM pages WHERE page_key = 'home'),
 'I need to search global bills of lading',
 'Access millions of bills of lading from ports worldwide. Our B/L search provides shipper and consignee details, product descriptions, quantities, and port information. Perfect for due diligence and market research.',
 'faq', 50, 'bills,lading,B/L,shipping,port'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I want to monitor supply chain risks',
 'Our risk monitoring dashboard tracks supply chain disruptions, port delays, and supplier reliability issues. Get real-time alerts when your key suppliers or trade routes face potential problems.',
 'faq', 49, 'supply,chain,risk,monitor,disruption'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I need to compare global product prices',
 'Compare product prices across different markets and suppliers. Our pricing analytics show average import/export values by country, helping you find the best sourcing opportunities.',
 'faq', 48, 'prices,compare,pricing,cost,value'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I want to find new export markets',
 'Discover high-demand markets for your products. Our market opportunity analysis identifies countries with growing imports in your product category, along with competitive landscape insights.',
 'faq', 47, 'export,markets,new,opportunity,demand'),

((SELECT id FROM pages WHERE page_key = 'home'),
 'I need trade data by HS Code',
 'Search our database using HS codes to find detailed trade statistics. View import/export volumes, top countries, pricing trends, and key players for any product classification.',
 'faq', 46, 'HS,code,tariff,classification,product');

-- ============================================================================
-- INSERT LOGISTICS FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
((SELECT id FROM pages WHERE page_key = 'logistics'),
 'Which importers need freight services?',
 'Our logistics intelligence identifies active importers who require freight forwarding services. View their shipment volumes, preferred routes, and current logistics partners to target your sales efforts effectively.',
 'suggested', 100, 'importers,freight,logistics,shipping'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'How do I analyze trade lanes?',
 'Our trade lane analytics show shipping volumes, transit times, and carrier performance for any origin-destination pair. Identify growing lanes and optimize your service offerings.',
 'suggested', 99, 'trade,lanes,routes,shipping,analyze'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'Which carriers have the highest volume?',
 'Compare carrier market share by trade lane, product type, or region. Our data shows shipping volumes, reliability metrics, and pricing trends for major carriers.',
 'suggested', 98, 'carriers,volume,shipping,lines,market'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'How can I monitor historical port activity?',
 'Track port throughput, vessel calls, and cargo volumes over time. Our port analytics help you identify trends, seasonal patterns, and capacity constraints.',
 'suggested', 97, 'port,activity,historical,vessels,throughput'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'Which exporters are active right now?',
 'See real-time export activity by country, product, or company. Our live data feed shows recent shipments, helping you identify active prospects for logistics services.',
 'suggested', 96, 'exporters,active,real-time,shipments'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'I need to find active exporters',
 'Search our database of exporters by product category, country, or shipment volume. View their shipping patterns and logistics requirements to tailor your service pitch.',
 'faq', 50, 'exporters,find,active,shipping'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'I want to track competitor routes',
 'Monitor competitor shipping patterns including routes, carriers used, and shipment frequencies. Identify their key accounts and service gaps you can fill.',
 'faq', 49, 'competitor,routes,track,shipping'),

((SELECT id FROM pages WHERE page_key = 'logistics'),
 'I need to identify high-volume shippers',
 'Find companies with significant shipping volumes that could benefit from your services. Filter by product type, trade lane, or growth rate.',
 'faq', 48, 'high-volume,shippers,big,frequent');

-- ============================================================================
-- INSERT PLATFORM FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
((SELECT id FROM pages WHERE page_key = 'platform'),
 'How do I map supply chains?',
 'Our supply chain mapping tool visualizes the complete network of suppliers, manufacturers, and buyers. Upload your data or search by company to see their trading relationships and dependencies.',
 'suggested', 100, 'supply,chain,map,visualize,network'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'Which partners are high risk?',
 'Our risk scoring algorithm evaluates trading partners based on financial stability, compliance history, and shipment reliability. Get alerts when risk levels change.',
 'suggested', 99, 'risk,partners,assessment,score,compliance'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'How can I download trade reports?',
 'Export detailed reports in PDF, Excel, or CSV format. Customize reports with your selected data fields, time periods, and company lists.',
 'suggested', 98, 'download,reports,export,PDF,Excel'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'How do I set shipment alerts?',
 'Configure real-time alerts for specific companies, products, or trade routes. Get notified via email or dashboard when matching shipments are recorded.',
 'suggested', 97, 'alerts,notifications,shipment,monitor'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'Which competitors are growing fast?',
 'Our growth analytics identify companies with rapidly increasing export/import volumes. See quarter-over-quarter and year-over-year growth rates by company or sector.',
 'suggested', 96, 'competitors,growing,growth,fast,trend'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'I want to visualize supply chains',
 'Create interactive supply chain diagrams showing material flows, company relationships, and geographic distribution. Export visualizations for presentations.',
 'faq', 50, 'visualize,supply,chain,diagram,interactive'),

((SELECT id FROM pages WHERE page_key = 'platform'),
 'I need to assess partner risk',
 'Run comprehensive risk assessments on potential partners including financial health, trade compliance, and operational reliability checks.',
 'faq', 49, 'assess,partner,risk,due,diligence');

-- ============================================================================
-- INSERT API FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
((SELECT id FROM pages WHERE page_key = 'api'),
 'How do I integrate trade data?',
 'Our REST API provides programmatic access to all trade data. Get started with our SDK libraries available for Python, JavaScript, and PHP. Full documentation includes code examples and rate limit information.',
 'suggested', 100, 'integrate,API,trade,data,SDK'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'Which endpoints provide company details?',
 'The /companies endpoint returns detailed company profiles including contact information, trade history, and risk scores. The /companies/search endpoint allows filtering by various criteria.',
 'suggested', 99, 'endpoints,company,details,profile'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'How can I search by HS Code?',
 'Use the /shipments endpoint with the hs_code parameter to filter results. Supports 2, 4, 6, or 8-digit HS codes. You can also use the /hs-codes endpoint to search code descriptions.',
 'suggested', 98, 'search,HS,code,API,endpoint'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'Which data formats are supported?',
 'API responses are available in JSON (default), XML, and CSV formats. Specify format using the Accept header or format query parameter. Bulk downloads support ZIP compression.',
 'suggested', 97, 'format,JSON,XML,CSV,response'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'How do I access historical data?',
 'Historical data is available through the date_from and date_to parameters. Premium plans include up to 10 years of historical data. Use pagination for large date ranges.',
 'suggested', 96, 'historical,data,archive,past,date'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'I want to integrate trade API',
 'Start by registering for an API key at our developer portal. Our quickstart guide walks you through authentication, making your first request, and handling responses.',
 'faq', 50, 'integrate,API,start,key,authenticate'),

((SELECT id FROM pages WHERE page_key = 'api'),
 'I need data by HS Code',
 'Query shipment data by HS code using our search endpoints. Returns detailed records including shipper, consignee, quantities, and values for matching products.',
 'faq', 49, 'HS,code,data,shipment,product');

-- ============================================================================
-- INSERT DATA LICENSE FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
((SELECT id FROM pages WHERE page_key = 'data_license'),
 'Which data formats are available?',
 'Licensed data is available in CSV, JSON, Parquet, and SQL dump formats. Choose the format that best fits your data pipeline. Custom schemas are available for enterprise clients.',
 'suggested', 100, 'format,CSV,JSON,Parquet,SQL'),

((SELECT id FROM pages WHERE page_key = 'data_license'),
 'How do I buy historical data?',
 'Contact our sales team for historical data licensing. Pricing depends on countries covered, date range, and data fields required. We offer one-time purchases and subscription models.',
 'suggested', 99, 'buy,historical,data,purchase,license'),

((SELECT id FROM pages WHERE page_key = 'data_license'),
 'I want to download historical data',
 'Historical data downloads are available for licensed customers. Access your data through our secure download portal or via scheduled SFTP delivery.',
 'suggested', 98, 'download,historical,data,bulk'),

((SELECT id FROM pages WHERE page_key = 'data_license'),
 'I need custom data reports',
 'Our data team can create custom extracts and reports tailored to your specific requirements. Tell us your criteria and delivery preferences.',
 'suggested', 97, 'custom,reports,data,extract'),

((SELECT id FROM pages WHERE page_key = 'data_license'),
 'I need bulk analysis at scale',
 'Enterprise data licenses include unlimited API calls, bulk download access, and dedicated support. Contact us for volume pricing.',
 'suggested', 96, 'bulk,scale,enterprise,volume');

-- ============================================================================
-- INSERT SEARCH DATA / COVERAGE FAQs
-- ============================================================================
INSERT INTO faq (page_id, question, answer, question_type, priority, keywords) VALUES
((SELECT id FROM pages WHERE page_key = 'search_data'),
 'Which fields are included in data?',
 'Our standard data includes: shipper name/address, consignee name/address, HS code, product description, quantity, weight, value, origin country, destination country, port names, and shipment date. Premium data adds contact details and company profiles.',
 'suggested', 100, 'fields,data,included,columns'),

((SELECT id FROM pages WHERE page_key = 'search_data'),
 'I need to check country coverage',
 'We cover 100+ countries with varying data depth. Major markets include USA, China, India, EU countries, and Latin America. Check our coverage page for country-specific details and data availability.',
 'suggested', 99, 'coverage,country,countries,available'),

((SELECT id FROM pages WHERE page_key = 'search_data'),
 'Which Asian countries are covered?',
 'Our Asian coverage includes China, India, Vietnam, Indonesia, Thailand, Malaysia, Philippines, South Korea, Japan, Taiwan, Bangladesh, Pakistan, and Sri Lanka. Import and export data availability varies by country.',
 'suggested', 98, 'Asia,Asian,China,India,Vietnam'),

((SELECT id FROM pages WHERE page_key = 'search_data'),
 'Which African markets are available?',
 'We cover major African markets including South Africa, Nigeria, Kenya, Egypt, Morocco, Ghana, and Tanzania. Coverage is expanding - contact us for specific country availability.',
 'suggested', 97, 'Africa,African,South Africa,Nigeria,Kenya'),

((SELECT id FROM pages WHERE page_key = 'search_data'),
 'I need data from South America',
 'South American coverage includes Brazil, Argentina, Chile, Colombia, Peru, Ecuador, and Uruguay. Our Latin American data includes detailed customs records with product and company information.',
 'suggested', 96, 'South America,Latin,Brazil,Argentina,Chile');

-- View all FAQs with page info
-- SELECT p.page_name, f.question, f.answer, f.question_type, f.priority
-- FROM faq f JOIN pages p ON f.page_id = p.id
-- ORDER BY p.page_name, f.priority DESC;
