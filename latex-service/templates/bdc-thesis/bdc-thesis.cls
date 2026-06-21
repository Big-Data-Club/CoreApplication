\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{bdc-thesis}[2026/06/21 BDC Thesis Class]

\LoadClass[12pt,a4paper,oneside]{report}

\RequirePackage{geometry}
\geometry{top=3cm,bottom=3cm,left=3.5cm,right=2.5cm}

\RequirePackage{titlesec}
\titleformat{\chapter}[display]
  {\normalfont\large\bfseries\centering}
  {\chaptertitlename\ \thechapter}
  {10pt}
  {\Large}

% Custom macros
\newcommand{\advisor}[1]{\def\@advisor{#1}}
\newcommand{\department}[1]{\def\@department{#1}}

\renewcommand{\maketitle}{
  \begin{titlepage}
    \centering
    \vspace*{1.5cm}
    {\large\bfseries HỒ CHÍ MINH UNIVERSITY OF TECHNOLOGY}\\[0.5cm]
    {\large\bfseries BIG DATA CLUB (BDC)}\\[2.5cm]
    
    {\Large\bfseries LUẬN VĂN TỐT NGHIỆP}\\[1.5cm]
    
    {\LARGE\bfseries \@title}\\[2.5cm]
    
    \begin{flushleft}
      \large
      \textbf{Sinh viên thực hiện:} \@author\\[0.3cm]
      \textbf{Giảng viên hướng dẫn:} \@advisor\\[0.3cm]
      \textbf{Bộ môn:} \@department
    \end{flushleft}
    
    \vfill
    {\large \@date}
  \end{titlepage}
}
