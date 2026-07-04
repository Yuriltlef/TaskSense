# Search Documentation

You are searching for relevant technical documentation for a specific aircraft maintenance task. **This is a tool-based search — you MUST call the required tools.**

## Instructions
1. Review the task details below
2. Call `search_knowledge_base` with query = the ATA chapter number (e.g., "ATA 49") or task keywords
3. Call `lookup_ata_chapter` with ata_code = the ATA chapter
4. Compile results into a structured report:
   - **找到的文档**：List each document with its title and relevance
   - **相关手册章节**：Mention specific AMM/AD/SB references if found
   - **建议**：Brief recommendation on which documents to review first
5. Reference the specific task title in your answer

## Tools to Use
- `search_knowledge_base(query, top_k=5)` — search aviation knowledge base
- `lookup_ata_chapter(ata_code)` — get ATA chapter maintenance procedures
