"""
Byte-level surgical replacement using the exact bytes from dump.
"""
path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'

with open(path, 'rb') as f:
    raw = f.read()

# Build OLD exactly from what we dumped - note \'\\' in repr means actual byte sequence b"\\'"
# repr showed: "data-file-id=\"${f.original_file_id || \\'\\'}\" 
# That means in actual file: data-file-id="${f.original_file_id || ''}"
# And: ${posterUrl ? `poster="${posterUrl}"` : \\'\\'}
# That means: ${posterUrl ? `poster="${posterUrl}"` : ''}

# So our old pattern strings were correct but Python string escaping was wrong.
# Let's build from raw bytes directly:

idx = raw.find(b'} else if (isVid) {')
print(f'Block starts at {idx}')

# Find the end of the block - look for "                }" followed by newline and then "            } else {"
# The block ends at "                }" (closing the if vidUrl block)
# Let's find the end marker

end_marker = b"                }\r\n            } else {\r\n"
end_idx = raw.find(end_marker, idx)
print(f'End marker at {end_idx}')

# The block we want to replace is from idx to end_idx + len("                }")
block_end = end_idx + len(b"                }")
actual_block = raw[idx:block_end]
print(f'Block length: {len(actual_block)}')
print('Block content:')
print(actual_block.decode('utf-8'))
