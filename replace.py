import os
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    original_content = content
    
    # 1. `initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}`
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*height:\s*0\s*\}\}\s*animate=\{\{\s*opacity:\s*1,\s*height:\s*\'auto\'\s*\}\}\s*exit=\{\{\s*opacity:\s*0,\s*height:\s*0\s*\}\}', 
                     r'variants={expandHeight} initial="initial" animate="animate" exit="exit"', content)
                     
    # Multi-line version of expandHeight
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*height:\s*0\s*\}\}\n\s*animate=\{\{\s*opacity:\s*1,\s*height:\s*\'auto\'\s*\}\}\n\s*exit=\{\{\s*opacity:\s*0,\s*height:\s*0\s*\}\}',
                     r'variants={expandHeight}\n            initial="initial"\n            animate="animate"\n            exit="exit"', content)

    # 2. `initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}` (and exit)
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*x:\s*-10\s*\}\}\s*animate=\{\{\s*opacity:\s*1,\s*x:\s*0\s*\}\}(\s*exit=\{\{\s*opacity:\s*0,\s*x:\s*-10\s*\}\})?',
                     r'variants={listItemSlide} initial="initial" animate="animate" exit="exit"', content)

    # Multi-line version of listItemSlide
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*x:\s*-10\s*\}\}\n\s*animate=\{\{\s*opacity:\s*1,\s*x:\s*0\s*\}\}',
                     r'variants={listItemSlide}\n            initial="initial"\n            animate="animate"\n            exit="exit"', content)

    # 3. `initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}` (and exit)
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*y:\s*-10\s*\}\}\s*animate=\{\{\s*opacity:\s*1,\s*y:\s*0\s*\}\}(\s*exit=\{\{\s*opacity:\s*0,\s*y:\s*-10\s*\}\})?',
                     r'variants={slideDown} initial="initial" animate="animate" exit="exit"', content)

    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*y:\s*-10\s*\}\}\n\s*animate=\{\{\s*opacity:\s*1,\s*y:\s*0\s*\}\}',
                     r'variants={slideDown}\n            initial="initial"\n            animate="animate"\n            exit="exit"', content)

    # 4. `initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}`
    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*y:\s*10\s*\}\}\s*animate=\{\{\s*opacity:\s*1,\s*y:\s*0\s*\}\}',
                     r'variants={slideUp} initial="initial" animate="animate" exit="exit"', content)

    content = re.sub(r'initial=\{\{\s*opacity:\s*0,\s*y:\s*10\s*\}\}\n\s*animate=\{\{\s*opacity:\s*1,\s*y:\s*0\s*\}\}',
                     r'variants={slideUp}\n            initial="initial"\n            animate="animate"\n            exit="exit"', content)

    # 5. `initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}`
    content = re.sub(r'initial=\{\{\s*height:\s*0,\s*opacity:\s*0\s*\}\}\s*animate=\{\{\s*height:\s*\'auto\',\s*opacity:\s*1\s*\}\}\s*exit=\{\{\s*height:\s*0,\s*opacity:\s*0\s*\}\}',
                     r'variants={expandHeight} initial="initial" animate="animate" exit="exit"', content)
                     
    content = re.sub(r'initial=\{\{\s*height:\s*0,\s*opacity:\s*0\s*\}\}\n\s*animate=\{\{\s*height:\s*\'auto\',\s*opacity:\s*1\s*\}\}\n\s*exit=\{\{\s*height:\s*0,\s*opacity:\s*0\s*\}\}',
                     r'variants={expandHeight}\n                      initial="initial"\n                      animate="animate"\n                      exit="exit"', content)

    # 6. `initial={{ opacity: 0 }} animate={{ opacity: 1 }}` (and exit)
    content = re.sub(r'initial=\{\{\s*opacity:\s*0\s*\}\}\s*animate=\{\{\s*opacity:\s*1\s*\}\}(\s*exit=\{\{\s*opacity:\s*0\s*\}\})?',
                     r'variants={fadeIn} initial="initial" animate="animate" exit="exit"', content)

    content = re.sub(r'initial=\{\{\s*opacity:\s*0\s*\}\}\n\s*animate=\{\{\s*opacity:\s*1\s*\}\}(\n\s*exit=\{\{\s*opacity:\s*0\s*\}\})?',
                     r'variants={fadeIn}\n            initial="initial"\n            animate="animate"\n            exit="exit"', content)

    if content != original_content:
        # Check imports to add variants if needed
        variants_used = []
        if 'expandHeight' in content: variants_used.append('expandHeight')
        if 'listItemSlide' in content: variants_used.append('listItemSlide')
        if 'slideDown' in content: variants_used.append('slideDown')
        if 'slideUp' in content: variants_used.append('slideUp')
        if 'fadeIn' in content: variants_used.append('fadeIn')
        
        if variants_used:
            imports_str = f"import {{ {', '.join(variants_used)} }} from '../lib/animations';"
            # If the file already imports from '../lib/animations', just let it be or replace it.
            if '../lib/animations' not in content:
                # Add import right after framer-motion or react imports
                if 'framer-motion' in content:
                    content = re.sub(r"(import .* from 'framer-motion';)", r"\1\n" + imports_str, content)
                else:
                    content = imports_str + "\n" + content
            else:
                # Naive fix to update imports if needed, but since we are script replacing let's manually do it if it fails.
                pass

        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('frontend/src'):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            if 'animations.ts' in file:
                continue
            process_file(os.path.join(root, file))
