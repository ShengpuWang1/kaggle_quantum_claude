import PyPDF2

pdf_path = '/Users/spwang/Documents/Quant/kaggle_quantum_claude/docs/papers/1805.12445.pdf'
pdf = PyPDF2.PdfReader(pdf_path)

text = ''
for i, page in enumerate(pdf.pages[:5]):
    page_text = page.extract_text()
    text += f"\n--- Page {i+1} ---\n{page_text}"

print(text[:5000])
