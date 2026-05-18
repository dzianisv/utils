# Download the page
wget -O article.html https://lilianweng.github.io/posts/2023-06-23-agent/

# Convert to EPUB (Kindle supports EPUB natively now)
pandoc article.html -o article.epub --metadata title="LLM Agents"

# Or to MOBI via Calibre's CLI tool
ebook-convert article.html article.mobi

