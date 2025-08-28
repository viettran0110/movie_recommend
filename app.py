import pickle
import streamlit as st
import requests

# Cache poster API call
@st.cache_data
def fetch_poster(movie_id):
    API_KEY = st.secrets["tmbd"]["api_key"]
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={API_KEY}&language=en-US"
    response = requests.get(url)
    data = response.json()
    poster_path = data.get('poster_path', None)
    if poster_path:
        return f"https://image.tmdb.org/t/p/w500/{poster_path}"
    return "https://via.placeholder.com/500x750?text=No+Image"

# Cache pickle loading
@st.cache_resource
def load_data():
    movies = pickle.load(open('artifacts/movie_list.pkl','rb'))
    similarity = pickle.load(open('artifacts/similarity.pkl','rb'))
    return movies, similarity

movies, similarity = load_data()

def recommend(movie, n=5):
    index = movies[movies['title'] == movie].index[0]
    distances = sorted(list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1])
    names, posters = [], []
    for i in distances[1:n+1]:
        movie_id = movies.iloc[i[0]].movie_id
        posters.append(fetch_poster(movie_id))
        names.append(movies.iloc[i[0]].title)
    return names, posters

# UI
st.header('Movie Recommender')
movie_list = movies['title'].values
selected_movie = st.selectbox("Type or select a movie", movie_list)

if st.button('Show Recommendation'):
    names, posters = recommend(selected_movie)
    cols = st.columns(len(names))
    for col, name, poster in zip(cols, names, posters):
        with col:
            st.text(name)
            st.image(poster)
