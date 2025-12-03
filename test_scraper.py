"""Test script to debug scraper output"""
from web_scraper import WebScraper

# Test scraping
scraper = WebScraper(timeout=15)
result = scraper.scrape_url('https://www.exportgenius.in/mirror-import-data/afghanistan/oil.php')

if result['success']:
    content = result['content']

    # Write to file to avoid encoding issues
    with open('scraper_test_output.txt', 'w', encoding='utf-8') as f:
        f.write(f"Total content length: {len(content)} chars\n")
        f.write("=" * 80 + "\n")

        # Find HS Code section
        hs_index = content.find('HS Code')
        f.write(f"'HS Code' found at position: {hs_index}\n\n")

        if hs_index != -1:
            # Write content around HS Code section
            start = max(0, hs_index - 200)
            end = min(len(content), hs_index + 2000)
            f.write("CONTENT AROUND 'HS CODE' SECTION:\n")
            f.write("=" * 80 + "\n")
            f.write(content[start:end])
            f.write("\n" + "=" * 80 + "\n\n")

        # Check for specific HS codes
        f.write("Searching for specific HS codes:\n")
        test_codes = ['1512199002', '1511902000', '1512119101', '1512299000', '17049090']
        for code in test_codes:
            if code in content:
                f.write(f"  FOUND {code}\n")
                # Show context
                idx = content.find(code)
                f.write(f"    Context: ...{content[max(0,idx-50):idx+100]}...\n")
            else:
                f.write(f"  NOT found {code}\n")

        # Test chunking
        f.write("\n" + "=" * 80 + "\n")
        f.write("CHUNKING TEST:\n")
        f.write("=" * 80 + "\n")
        chunks = scraper.chunk_scraped_content(content, chunk_size=1000, overlap=100)
        f.write(f"Total chunks: {len(chunks)}\n\n")

        # Write all chunks
        for i, chunk in enumerate(chunks):
            f.write(f"\n{'='*80}\n")
            f.write(f"CHUNK {i+1} ({len(chunk)} chars)\n")
            f.write(f"{'='*80}\n")
            f.write(chunk)
            f.write(f"\n{'='*80}\n")

    print("Test complete! Output written to: scraper_test_output.txt")
    print(f"Total content: {len(content)} chars")
    print(f"Total chunks: {len(chunks)}")

else:
    print(f"Scraping failed: {result['error']}")
