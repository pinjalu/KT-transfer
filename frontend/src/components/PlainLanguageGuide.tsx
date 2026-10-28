/** Reading help, kept separate from claims generated about the selected project. */
const GUIDES: Record<string, { intro: string; words: [string, string][] }> = {
  purpose: {
    intro: 'Start with the job this project does. Look for who uses it, what they need, and how it helps them.',
    words: [['Project', 'A set of files that work together to do a job.'], ['Feature', 'Something the project lets a person do.']],
  },
  technologies: {
    intro: 'Software is built using tools, just as a house is built using tools and materials. This section explains which tools this project uses and what each one helps with.',
    words: [['Library or package', 'Ready-made code that a project can use.'], ['Framework', 'A starting structure for building a program.'], ['Dependency', 'Another tool or package the project needs.']],
  },
  architecture: {
    intro: 'Think of the code as a team. Different files have different jobs. This section explains those jobs and how the parts work together.',
    words: [['Architecture', 'How the parts of a program are arranged.'], ['Module', 'A file or group of code with a particular job.'], ['Function', 'A named set of instructions that does a task.']],
  },
  setup: {
    intro: 'This is the starting checklist: what you need, what to install, and how to open the program. Follow only the commands that the project files actually show.',
    words: [['Command', 'An instruction you type into a terminal.'], ['Terminal', 'A window where you give the computer written instructions.'], ['Environment variable', 'A named setting supplied when a program runs.']],
  },
  flows: {
    intro: 'Follow one action from beginning to end: what starts it, what the program does next, and what comes back. Missing steps are pointed out instead of guessed.',
    words: [['Request', 'An instruction or question sent to a program.'], ['Response', 'What the program sends back.'], ['Workflow', 'The steps needed to finish a task.']],
  },
  interfaces: {
    intro: 'This section explains the ways someone can ask the program to do a job. It shows what to send and what comes back when the files provide that information.',
    words: [['API', 'A way for one program to ask another program for something.'], ['Endpoint or route', 'An address a program listens to for a particular request.'], ['Input and output', 'What goes into a program and what comes out.']],
  },
  data: {
    intro: 'Programs often need to remember things. This section explains what this project saves, where it keeps it, and which settings change how it works.',
    words: [['Database', 'An organised place to keep information.'], ['Table and row', 'A table is like a list; each row holds one entry.'], ['Configuration', 'Settings that tell a program how to work.']],
  },
  testing: {
    intro: 'A test gives the program an example and checks the result. This section shows which checks were found and how to run them. Finding a test does not mean it has passed.',
    words: [['Test', 'A check that compares a result with what was expected.'], ['Assertion', 'The rule a test checks.'], ['Deployment', 'Putting a program somewhere people can use it.']],
  },
  decisions: {
    intro: 'Read what the team asked for, suggested, or agreed to. An idea in a conversation is different from a change already made in the code.',
    words: [['Ticket', 'A written task, request, or problem.'], ['Proposal', 'An idea someone has suggested.'], ['Decision', 'A choice the team has recorded as agreed.']],
  },
  _features: {
    intro: 'A feature is one job the project can do. Choose a group to learn how that job works and which files are involved.',
    words: [['Route', 'An address used to ask the program to do a job.'], ['Gap', 'Something the files do not show or explain.']],
  },
  _facts: {
    intro: 'These details come directly from the project files. Open a group to see the names, settings, or commands that were found.',
    words: [['Dependency', 'Another package the project needs.'], ['Source line', 'A numbered line in a file that you can read to check a detail.']],
  },
  _reading: {
    intro: 'You do not need to read every file at once. Follow this list one file at a time and mark the ones you have read.',
    words: [['README', 'A file that usually introduces the project and explains how to use it.']],
  },
  _review: {
    intro: 'This page tells you what was read and what still needs checking. If something is missing, that does not prove the project cannot do it.',
    words: [['Coverage', 'How much of the project was included in this read.'], ['Snapshot', 'A saved copy of the files at one point in time.']],
  },
}

export function PlainLanguageGuide({ topic }: { topic: string }) {
  const guide = GUIDES[topic]
  if (!guide) return null
  return <aside className="ov-simple-guide" aria-label="Help for new readers">
    <details><summary>Words made simple</summary>
      <p>{guide.intro}</p>
      <dl>{guide.words.map(([word, meaning]) => <div key={word}><dt>{word}</dt><dd>{meaning}</dd></div>)}</dl>
    </details>
  </aside>
}
