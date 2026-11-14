import { writeFile, rename } from 'node:fs/promises'
import { format, resolveConfig } from 'prettier'

let input = ''
for await (const chunk of process.stdin) input += chunk
const snapshot = JSON.parse(input)
if (!snapshot.generated_at || snapshot.examples?.length !== 4)
  throw new Error('Invalid landing snapshot')
for (const example of snapshot.examples) {
  if (
    !example.category ||
    !example.question ||
    !example.answer ||
    !example.source_label ||
    !example.features?.length ||
    !example.sources?.length
  )
    throw new Error('Incomplete real example')
}
const files = [
  ['landing-data.json', snapshot],
  ['example-questions.json', snapshot.examples.map(({ question }) => question)],
]
for (const [name, data] of files) {
  const target = new URL(`../src/chat/${name}`, import.meta.url)
  const temporary = new URL(`../src/chat/${name}.tmp`, import.meta.url)
  await writeFile(
    temporary,
    await format(JSON.stringify(data), {
      ...(await resolveConfig(target.pathname)),
      parser: 'json',
    }),
  )
  await rename(temporary, target)
}
console.log(`Updated ${snapshot.examples.length} public examples (${snapshot.generated_at})`)
