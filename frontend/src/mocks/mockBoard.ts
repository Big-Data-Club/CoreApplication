import type { Column } from '@/types';

export const initialColumns: Column[] = [
  {
    id: "todo",
    title: "TODO",
    color: "bg-slate-500",
    tasks: [
      {
        id: "task1",
        title: "Prepare presentation for Event 1",
        description: "Create slides for the main session",
        assignees: ["u1", "u3"],
        links: [
          { id: "link1", url: "https://docs.example.com/slides", title: "Slide Template" }
        ],
        startDate: "2026-07-06T15:30:00",
        endDate: "2026-07-06T17:30:00",
        columnId: "todo",
        eventId: "1"
      },
      {
        id: "task2",
        title: "Setup venue",
        description: "Arrange seating and equipment",
        assignees: ["u3"],
        links: [],
        startDate: "2026-07-06T07:30:00",
        endDate: "2026-07-06T10:30:00",
        columnId: "todo",
        eventId: "1"
      },
      {
        id: "task4",
        title: "Cater food",
        description: "Organize lunch for attendees",
        assignees: ["u4", "u5"],
        links: [],
        startDate: "2026-07-08T10:00:00",
        endDate: "2026-07-08T19:30:59",
        columnId: "todo",
        eventId: "3"
      },
    ]
  },
  {
    id: "in-progress",
    title: "In Progress",
    color: "bg-blue-500",
    tasks: [
      {
        id: "task3",
        title: "Send invitations",
        description: "Email invitations to participants",
        assignees: ["u2"],
        links: [
          { id: "link2", url: "https://invite.example.com", title: "Invitation Form" }
        ],
        startDate: "2026-07-09T00:00:00",
        endDate: "2026-07-09T03:59:59",
        columnId: "in-progress",
        eventId: "2"
      },
      {
        id: "task6",
        title: "Design posters",
        description: "Create promotional materials",
        assignees: ["u1", "u2"],
        links: [
          { id: "link4", url: "https://design.example.com", title: "Design Tool" }
        ],
        startDate: "2026-07-04T07:00:00",
        endDate: "2026-07-04T07:59:59",
        columnId: "in-progress",
        eventId: "4"
      },
      {
        id: "task7",
        title: "Test AV equipment",
        description: "Ensure audio-visual setup works",
        assignees: ["u3", "u4"],
        links: [],
        startDate: "2026-07-05T17:00:00",
        endDate: "2026-07-05T18:30:00",
        columnId: "in-progress",
        eventId: "4"
      }
    ]
  },
  {
    id: "done",
    title: "Done",
    color: "bg-green-500",
    tasks: [
      {
        id: "t4",
        title: "Setup CI/CD pipeline",
        description: "Cấu hình GitHub Actions cho auto deployment",
        assignees: ["u5"],
        links: [{ id: "l4", url: "https://github.com/actions", title: "GitHub Actions" }],
        startDate: "2025-10-01T00:00:00",
        endDate: "2025-10-08T23:59:59",
        columnId: "done",
        eventId: "4",
      }
    ]
  },
  {
    id: "cancel",
    title: "Cancel",
    color: "bg-red-500",
    tasks: [
      {
        id: "task5",
        title: "Book guest speaker",
        description: "Confirm speaker availability",
        assignees: ["u2"],
        links: [
          { id: "link3", url: "https://speaker.example.com", title: "Speaker Profile" }
        ],
        startDate: "2026-07-06T00:00:00",
        endDate: "2026-07-07T23:59:59",
        columnId: "cancel",
        eventId: "3"
      }
    ]
  }
];