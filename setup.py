from setuptools import setup, find_packages

setup(
    name="movie_recommender",   # tên package, có thể tuỳ chỉnh
    version="0.0.1",
    description="Movie Recommender System with Streamlit",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        "streamlit",
        "pandas",
        "numpy",
        "scikit-learn",
        "requests"
    ],
)
