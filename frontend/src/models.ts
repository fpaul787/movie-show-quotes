export type Quote = {
  id: number;
  text: string;
  language: string;
  tags: string[];
  character: { id: number; name: string } | null;
  media: {
    id: number;
    title: string;
    media_type: "MOVIE" | "TV_SHOW";
    release_year: number;
  };
};